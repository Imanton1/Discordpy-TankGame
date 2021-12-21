from collections import Counter
import datetime
import json
import math
import random
from PIL import Image

state_pregame = 0
state_game = 1

class NotEnoughHealth(Exception):
    pass
class UnknownCommand(Exception):
    pass
class NotEnoughAP(Exception):
    pass
class NotInRange(Exception):
    pass
class BadDirection(Exception):
    pass
class PlayerNotInGame(Exception):
    pass
class GameJoinError(Exception):
    pass

#https://stackoverflow.com/questions/43864101/python-pil-check-if-image-is-transparent
def has_transparency(img):
    if img.mode == "P":
        transparent = img.info.get("transparency", -1)
        for _, index in img.getcolors():
            if index == transparent:
                return True
    elif img.mode == "RGBA":
        extrema = img.getextrema()
        if extrema[3][0] < 255:
            return True
    return False

def playercount_to_size(pc):
    """
    Generate board whose area is approx 15 spaces / player
    And whose ratio is approx the golden ratio

    Probably some graph theory here to get a good number
    """
    # magic = sqrt(GOLDEN_RATIO)
    magic = 1.272019650
    x = math.ceil(math.sqrt(15 * pc) * magic)
    y = math.ceil(math.sqrt(15 * pc) / magic)

    if y > 26:  #height is limited by the alphabet
        y = 26  #
        x = 15 * pc / 26

    return [x, y]

def distance(player1, player2):
    """
    returns the manhattan distance between two players
    """
    return max(
        player1["X"]-player2["X"], player2["X"]-player1["X"],
        player1["Y"]-player2["Y"], player2["Y"]-player1["Y"]
        )

directions = {
    "7":              (-1, 1),
    "nw":             (-1, 1),
    "northwest":      (-1, 1),
    "ul":             (-1, 1),
    "upleft":         (-1, 1),
    "8":              ( 0, 1),
    "n":              ( 0, 1),
    "north":          ( 0, 1),
    "u":              ( 0, 1),
    "up":             ( 0, 1),
    "9":              ( 1, 1),
    "ne":             ( 1, 1),
    "northeast":      ( 1, 1),
    "ur":             ( 1, 1),
    "upright":        ( 1, 1),
    "4":              (-1, 0),
    "w":              (-1, 0),
    "west":           (-1, 0),
    "l":              (-1, 0),
    "left":           (-1, 0),
    "6":              ( 1, 0),
    "e":              ( 1, 0),
    "east":           ( 1, 0),
    "r":              ( 1, 0),
    "right":          ( 1, 0),
    "1":              (-1,-1),
    "sw":             (-1,-1),
    "southwest":      (-1,-1),
    "dl":             (-1,-1),
    "downleft":       (-1,-1),
    "2":              ( 0,-1),
    "s":              ( 0,-1),
    "south":          ( 0,-1),
    "d":              ( 0,-1),
    "down":           ( 0,-1),
    "3":              ( 1,-1),
    "se":             ( 1,-1),
    "southeast":      ( 1,-1),
    "dr":             ( 1,-1),
    "downright":      ( 1,-1),
}

def direction_upness(dir):
    """
    Takes in a string direction and returns the partial direction
    """
    try:
        return directions[dir.lower()][1]
    except KeyError:
        raise BadDirection("Not a known direction")

def direction_rightness(dir):
    """
    Takes in a string direction and returns the partial direction
    """
    try:
        return directions[dir.lower()][0]
    except KeyError:
        raise BadDirection("Not a known direction")

class tank_game():
    def __init__(self, who_id=None, *, time_gap=datetime.timedelta(hours=24), time_delta=datetime.timedelta(hours=0), skip_on_0=False):
        self.players = {}               #who is in the game
        self.state = state_pregame      #loading the players up
        self.board_size = [1,1]         #remember board size
        self.owner = who_id             #who starts the game
        self.time_gap = time_gap        #how quickly do people get AP
        self.time_delta = time_delta    #how quickly between the first and last person geting AP
        self.next_time = datetime.datetime.now()    #when did we last get AP
        self.skip_on_0 = skip_on_0      #Do you skip the remaining time when everyone has 0 AP?
        self.hearts = []                #Positions of random hearts on the board.
        self.version = 1                #1 = post-time-delta

    def save_state(self):
        return json.dumps({
            "state": self.state,
            "board_size": self.board_size,
            "owner": self.owner,
            "players": self.players,
            "skip_on_0": self.skip_on_0,
            "hearts": self.hearts,
            "version": self.version,

            "next_time": self.next_time.strftime("%Y-%m-%d %H:%M:%S"),
            "time_gap": self.time_gap.total_seconds(),
            "time_delta": self.time_delta.total_seconds(),
            })

    def load_state(self, loadstring):
        data = json.loads(loadstring)

        self.state = data["state"]
        self.board_size = data["board_size"]
        self.owner = data["owner"]
        self.skip_on_0 = data["skip_on_0"]
        self.hearts = data["hearts"]
        try:
            self.version = data["version"]
        except KeyError:
            self.version = 0

        self.players = {}
        for id_p, val in data["players"].items():
            self.players[int(id_p)] = val

        self.next_time = datetime.datetime.strptime(data["next_time"], "%Y-%m-%d %H:%M:%S")
        self.time_gap = datetime.timedelta(seconds=data["time_gap"])
        try:
            self.time_delta = datetime.timedelta(seconds=data["time_delta"])
        except KeyError:
            self.time_delta = datetime.timedelta(seconds=0)

    def save_state_to_file(self, file):
        """
        Writes the game object to a file
        """
        with open(file, 'w') as f:
            f.write(self.save_state())

    def load_state_from_file(self, file):
        """
        Reads the game object from a file
        """
        with open(file, 'r') as f:
            self.load_state(f.read())

    def active(self):
        return self.state == state_game

    def selector_in_game(self, who_id, first_person=True):
        """
        Selector
        """
        if who_id not in self.players:
            if first_person:
                raise PlayerNotInGame("You are not in the game!")
            else:
                raise PlayerNotInGame("Player not in the game!")

    def selector_alive(self, who_id, first_person=True):
        """
        Selector
        """
        if self.players[who_id]["HP"] == 0:
            if first_person:
                raise NotEnoughHealth("You are dead!")
            else:
                raise NotEnoughHealth("Target is dead!")

    def selector_minimum_AP(self, who_id, ap):
        """
        Selector
        """
        if self.players[who_id]["AP"] < ap:
            raise NotEnoughAP("You don't have enough AP!")

    def selector_range(self, who_id, target):
        """
        Selector
        """
        if distance(self.players[who_id], self.players[target]) > self.players[who_id]['range']:
            raise NotInRange("Target is not in range!")

    def selector_not_self(self, who_id, target):
        """
        Selector
        """
        if who_id == target:
            raise NotEnoughHealth("You can't target yourself!")

    def insert_player(self, who_id):
        """
        Adds a player to the game.
        """
        # don't add the same person twice
        if who_id in self.players:
            raise GameJoinError("Player already in game")

        #don't add while the game is in progress
        elif self.state != state_pregame:
            raise GameJoinError("Game already started")

        else:
            self.players[who_id] = {"HP": 3, "range": 2, "X": 0, "Y": 0, "AP": 0, "haunting": None, "skip_turn": False}
        return "You joined the game!"

    def start_game(self, who_id):
        if self.state != state_pregame:
            raise GameJoinError("Game already started")
        elif who_id != self.owner:
            raise GameJoinError("You are not allowed to start the game.")
        elif len(self.players) < 2:
            raise GameJoinError("Not enough players to start the game (Min 2).")
        else:
            # set game as being played
            self.state = state_game

            #set start time
            self.next_time = datetime.datetime.now()

            # set board size
            self.board_size = playercount_to_size(len(self.players))

            # make sure player doesn't spawn on top of another player
            locs = random.sample(range(0, self.board_size[0] * self.board_size[1] - 1), len(self.players))

            for i, p in enumerate(self.players):
                self.players[p]["X"] = locs[i] % self.board_size[0]
                self.players[p]["Y"] = locs[i] // self.board_size[0]
        return "Started the game!"

    def is_playable(self):
        """
        Does something to indicate that the game is over
        """
        alive_count = 0
        for p in self.players.values():
            if p["HP"] >= 1:
                alive_count += 1
        return alive_count >= 2

    def move(self, who_id, direction):
        self.selector_in_game(who_id)
        self.selector_alive(who_id)
        self.selector_minimum_AP(who_id, 1)

        #make sure still on board
        if not 0 <= (self.players[who_id]["X"]+direction_rightness(direction)) < self.board_size[0]:
            raise BadDirection("Can't leave the board.")
        if not 0 <= (self.players[who_id]["Y"]-direction_upness(direction)) < self.board_size[1]:
            raise BadDirection("Can't leave the board.")

        for i in self.players.values():
            if (self.players[who_id]["X"]+direction_rightness(direction)) == i["X"] and\
                (self.players[who_id]["Y"]-direction_upness(direction)) == i["Y"]:
                raise BadDirection("Can't stand on another player.")


        self.players[who_id]["AP"] -= 1
        self.players[who_id]["X"] += direction_rightness(direction)
        self.players[who_id]["Y"] -= direction_upness(direction)

        # pick up hearts
        playerpos = [self.players[who_id]["X"], self.players[who_id]["Y"]]
        heartcount = self.hearts.count(playerpos)
        self.players[who_id]["HP"] += heartcount
        for i in range(heartcount):
            self.hearts.remove(playerpos)

        return "Moved {}".format(direction)

    def attack(self, who_id, target):
        self.selector_in_game(who_id)
        self.selector_in_game(target, False)
        self.selector_alive(who_id)
        self.selector_alive(target, False)
        self.selector_minimum_AP(who_id, 1)
        self.selector_not_self(who_id, target)

        if self.players[target]["HP"] == 0:
            raise NotEnoughHealth("Target is already dead!")       # make sure not dead
        self.selector_range(who_id, target)


        self.players[target]["HP"] -= 1                              # do one damage
        self.players[who_id]["AP"] -= 1
        if self.players[target]["HP"] == 0:                          # if dead
            ap = self.players[target]["AP"]
            self.players[who_id]["AP"] += self.players[target]["AP"] # give all AP
            self.players[target]["AP"] = 0
            return ("Killed <@{}>".format(target), "Stole {} AP.".format(ap))
        else:
            return ("Attacked <@{}>".format(target),)

    def giveAP(self, who_id, target):
        self.selector_in_game(who_id)
        self.selector_in_game(target, False)
        self.selector_alive(who_id)
        self.selector_alive(target, False)
        self.selector_minimum_AP(who_id, 1)
        self.selector_range(who_id, target)
        self.selector_not_self(who_id, target)

        self.players[who_id]["AP"] -= 1
        self.players[target]["AP"] += 1
        return "Gave 1 AP to <@{}>".format(target)

    def giveHP(self, who_id, target):
        self.selector_in_game(who_id)
        self.selector_in_game(target, False)
        self.selector_alive(who_id)
        self.selector_range(who_id, target)
        self.selector_not_self(who_id, target)

        self.players[who_id]["HP"] -= 1
        self.players[target]["HP"] += 1
        return "Gave 1 HP to <@{}>".format(target)

    def heal(self, who_id):
        self.selector_in_game(who_id)
        self.selector_alive(who_id)
        self.selector_minimum_AP(who_id, 3)

        self.players[who_id]["AP"] -= 3
        self.players[who_id]["HP"] += 1
        return "Healed!"

    def upgrade(self, who_id):
        self.selector_in_game(who_id)
        self.selector_alive(who_id)
        self.selector_minimum_AP(who_id, 3)

        self.players[who_id]["AP"] -= 3
        self.players[who_id]["range"] += 1
        return "Upgraded range!"

    def haunt(self, who_id, target):
        self.selector_in_game(who_id)
        self.selector_in_game(target, False)
        if self.players[who_id]["HP"] != 0:
            raise NotEnoughHealth("You are not dead enough to haunt!")
        self.selector_not_self(who_id, target)
        self.selector_alive(target, False)

        self.players[who_id]["haunting"] = target
        return "Haunting <@{}>!".format(target)

    def info(self, who_id):
        self.selector_in_game(who_id)
        return "You have {} AP and {} range".format(self.players[who_id]["AP"], self.players[who_id]["range"])

    def skip_turn(self, who_id):
        if self.players[who_id]["skip_turn"]:
            return "Already prepared to skip"
        else:
            self.players[who_id]["skip_turn"] = True
            return "Prepared to skip"

    def haunted_player(self):
        """
        returns the player with the most haunted votes
        Ties fail
        """
        haunting_counts = Counter([v["haunting"] for v in self.players.values() if v["HP"] == 0])
        haunted_players = haunting_counts.most_common(2)
        if len(haunted_players) == 0:
            return False

        if len(haunted_players) == 1:
            return haunted_players[0][0]

        if haunted_players[0][0] == haunted_players[1][0]:
            return False

        return haunted_players[0][0]

    def test_all_ready_ap(self):
        """
        if everyone is 0 AP or pass, give AP
        """
        if self.active() and self.skip_on_0 and all(v["skip_turn"] or v["AP"]==0 for p, v in self.players.items()):
            self.next_time = datetime.datetime.now()
            self.give_hourly_AP_all()
            return True
        return False

    def test_hourly_AP(self):
        """
        if the next time has passed, give AP
        """
        if self.active() and self.next_time < datetime.datetime.now():
            self.give_hourly_AP_all()
            return True
        return False

    def give_hourly_AP_all(self):
        haunted_player = self.haunted_player()
        for player in self.players:
            if player != haunted_player and self.players[player]["HP"] > 0:
                self.players[player]["AP"] += 1
                self.players[player]["skip_turn"] = False
        self.next_time += self.time_gap


        if not self.dead_game():
            # add heart to board
            while True:
                heartpos = [
                    random.randint(0, self.board_size[0]-1),
                    random.randint(0, self.board_size[1]-1)
                ]
                #prevent spawning on a player
                for i in self.players.values():
                    if i["X"] == heartpos[0] and i["Y"] == heartpos[1]:
                        break
                else:
                    break  # only executed if the inner loop did NOT break
                continue  # only executed if the inner loop DID break
            self.hearts.append(heartpos)

    def dead_game(self):
        return len(self.hearts) > 5*len(self.players)

    def get_all_players(self):
        return list(self.players.keys())

    def display(self, fname="maps/out.png", *, box_size=32, thickness=1):
        """
        Sends a grid of players to the channel.
        """
        #avatar_url_as(format="PNG", static_format='PNG', box_size_o=32)

        box_size_o = box_size + thickness
        board_w,board_h = self.board_size

        board_h += 1
        board_w += 1

        img = Image.new("RGB", (box_size_o*board_w+thickness-1, box_size_o*board_h+thickness-1), "white")
        pixels = img.load()

        for i in range(img.size[0]):
            for j in range(box_size_o-1, img.size[1], box_size_o):
                for k in range(thickness):
                    pixels[i, j+k] = 0

        for i in range(box_size_o-1, img.size[0], box_size_o):
            for j in range(img.size[1]):
                for k in range(thickness):
                    pixels[i+k, j] = 0

        #name the top row
        for i in range(1, board_w):
            try:
                subimg = Image.open("static_images/top/{}x{}.png".format(i, box_size), 'r')
            except FileNotFoundError:
                subimg = Image.open("D:/Documents/python/tank/static_images/5px.png", 'r')
            img.paste(subimg, (box_size_o*i+thickness-1, 0))

        #name the left coloum
        for i in range(1, board_h):
            try:
                subimg = Image.open("static_images/side/{}x{}.png".format(i, box_size), 'r')
            except FileNotFoundError:
                subimg = Image.open("D:/Documents/python/tank/static_images/5px.png", 'r')
            img.paste(subimg, (0, box_size_o*i+thickness-1))

        #preload the heart, as to not be loading it 30+ times
        heart = Image.open("./static_images/heart.png", 'r')
        width = 10

        #put players on the board
        for p,v in self.players.items():
            #player_img = Image.open("dynamic_images/{}x{}.png".format(p, box_size), 'r')

            #multiple = max(box_size // max(player_img.height, player_img.width), 1)
            #print("multiple: ", multiple, player_img.height, player_img.width)
            #player_img = player_img.resize( (multiple*player_img.height, multiple*player_img.width), Image.NEAREST)

            try:
                player_img = Image.open("dynamic_images/{}.png".format(p), 'r')
            except:
                player_img = Image.open("dynamic_images/{}x64.png".format(p), 'r')

            if player_img.width > box_size:
                #assume height==width, or have pain.
                player_img = player_img.resize( (box_size, box_size))
            else:
                multiple = box_size // player_img.width
                player_img = player_img.resize( (multiple*player_img.height, multiple*player_img.width), Image.NEAREST)

            p1 = box_size_o*(v["X"]+1)+thickness-1 + (box_size-player_img.width ) // 2
            p2 = box_size_o*(v["Y"]+1)+thickness-1 + (box_size-player_img.height) // 2
            if has_transparency(player_img):
                img.paste(player_img, (p1,p2), mask=player_img)
            else:
                img.paste(player_img, (p1,p2))

            #Also display health
            hp = v["HP"]
            for i in range(1,hp+1):
                img.paste(heart, (
                    int(p1+i*(box_size-width*hp)/(hp+1) + width*(i-1)),
                    int(p2+box_size*4/5-width/2)
                    ), mask=heart)

        for x,y in self.hearts:
            img.paste(heart, (
                int((x+1)*box_size_o + box_size/2 - width/2),
                int((y+1)*box_size_o + box_size/2 - width/2)
                ), mask=heart)

        img.save(fname)

if __name__ == '__main__':
    game = tank_game(269904594526666754)
    game.insert_player(269904594526666754)
    game.insert_player(619671441805279252)
    game.start_game(269904594526666754)

    #print(1, game.hearts)
    #game.give_hourly_AP_all()
    #print(2, game.hearts)

    game.display(box_size=64, thickness=2)
    #for i in range(2, 10):
    #    print(i, "players:", playercount_to_size(i)[0], "x", playercount_to_size(i)[1])

    #print(datetime.datetime.now().strftime())
