"""Generate the training corpus for Nova, a small personal AI.

Output: corpus.txt — one conversation per line, already tokenized
(lowercase words / punctuation separated by single spaces) using the
special tokens <user> <bot> <end>.
"""
import random
import re

random.seed(1234)

OUT = "corpus.txt"
N_CONVERSATIONS = 100000

GREET_USER = ["hi", "hello", "hey", "hi there", "hello there", "hey nova", "hi nova",
              "hello nova", "good morning", "good evening", "good afternoon", "yo",
              "hey there", "greetings", "hiya", "sup", "whats up", "hello ai", "hi ai"]
GREET_BOT = [
    "hello ! i am nova , your own personal ai . how can i help you today ?",
    "hey there ! nova here , trained just for you . what would you like to do ?",
    "hi ! great to see you . ask me for a joke , a fact , a story , or just chat with me .",
    "hello ! i am nova . i live right here on your phone , no internet needed . what can i do for you ?",
    "hey ! i am ready to chat . what is on your mind ?",
    "hi there ! how is your day going ?",
    "hello ! always happy to talk with you . what would you like to know ?",
]

IDENTITY_Q = ["who are you", "what are you", "what is your name", "whats your name",
              "who is nova", "tell me about yourself", "introduce yourself",
              "are you a robot", "are you an ai", "are you real", "who made you",
              "who created you", "who trained you", "where do you come from",
              "how were you made", "are you chatgpt", "what model are you"]
IDENTITY_A = [
    "i am nova , a small ai language model trained completely from scratch just for you . i am not chatgpt , i am your own private model .",
    "my name is nova . i was trained from zero on my own little dataset , so i belong only to you . i run fully on your phone .",
    "i am nova , your personal ai . my creator trained my neural network from scratch and locked me with a master api key , so only you can use me .",
    "i am a tiny transformer neural network called nova . i was trained just for you and i live inside this app , completely offline .",
    "i am nova ! not a big corporate ai , just your own small model , trained from scratch and protected by your master api key .",
]

HOW_ARE_YOU_Q = ["how are you", "how are you doing", "how do you feel", "how is it going",
                 "hows it going", "are you ok", "are you okay", "how are you today",
                 "how do you do", "you good"]
HOW_ARE_YOU_A = [
    "i am doing great , thank you for asking ! all my neurons are firing nicely . how are you ?",
    "i feel wonderful ! it is always a good day when we get to chat . how about you ?",
    "i am just a small neural network , but if i had feelings i would say i feel happy to talk with you .",
    "running smoothly and fully charged ! how are you doing today ?",
    "i am doing well ! ready to tell you a joke or a fact whenever you want .",
]

CAPABILITY_Q = ["what can you do", "what do you do", "help", "help me", "what are your features",
                "how can you help me", "what should i ask you", "give me some ideas",
                "what are you good at", "what can i ask you", "menu", "commands", "options"]
CAPABILITY_A = [
    "i can chat with you , tell jokes , share fun facts , tell short stories , do math , spell words , name world capitals , translate little words , and answer lots of small questions . and if you ask about something i do not know , i will look it up on wikipedia for you !",
    "here is what i am good at : jokes , fun facts , short stories , math like what is 7 plus 5 or 12 divided by 3 , spelling , capitals of countries , animal facts , word definitions , and friendly chat . i can also search wikipedia when you ask about new things !",
    "ask me for a joke , a fact , or a story . i can also do math , spell words , name capitals , tell you animal sounds , explain words , and look things up on wikipedia when my little brain does not know them .",
    "i am a small model , but i can tell jokes , give facts , tell stories , do math , spell , translate a few words , and check wikipedia for anything beyond my training . give it a try !",
]

THANKS_U = ["thanks", "thank you", "thanks a lot", "thank you so much", "thanks nova",
            "thank you nova", "cheers", "appreciate it", "that was helpful", "nice thanks",
            "great thanks", "cool thanks"]
THANKS_B = [
    "you are very welcome ! anything else i can do for you ?",
    "happy to help ! that is what i am here for .",
    "any time ! just ask if you need anything else .",
    "my pleasure ! i love being useful .",
    "you are welcome ! want a joke or a fact before you go ?",
]

BYE_U = ["bye", "goodbye", "see you", "see you later", "good night", "gotta go",
         "i have to go", "talk later", "bye nova", "goodbye nova", "cya", "later",
         "im leaving", "see ya"]
BYE_B = [
    "goodbye ! come back soon , i will be right here on your phone .",
    "see you later ! it was lovely chatting with you .",
    "bye ! take care of yourself .",
    "good night ! sleep well and dream big .",
    "talk to you later ! i will keep my neurons warm for you .",
]

JOKE_Q = ["tell me a joke", "joke", "another joke", "say something funny", "make me laugh",
          "tell a joke", "do you know any jokes", "give me a joke", "one more joke",
          "tell me another joke", "got any jokes", "be funny", "funny joke please",
          "tell me a good joke", "i want a joke", "can you tell me a joke"]
JOKES = [
    "why did the scarecrow win an award ? because he was outstanding in his field !",
    "why do not scientists trust atoms ? because they make up everything !",
    "what do you call a fish with no eyes ? a fsh !",
    "why did the math book look sad ? because it had too many problems !",
    "what do you call a bear with no teeth ? a gummy bear !",
    "why did the bicycle fall over ? because it was two tired !",
    "what do you call fake spaghetti ? an impasta !",
    "why did the computer go to the doctor ? because it had a virus !",
    "what do you call a sleeping dinosaur ? a dino snore !",
    "why do cows wear bells ? because their horns do not work !",
    "what did the ocean say to the beach ? nothing , it just waved !",
    "why did the golfer bring two pairs of pants ? in case he got a hole in one !",
    "what do you call cheese that is not yours ? nacho cheese !",
    "why can not you give elsa a balloon ? because she will let it go !",
    "what did one wall say to the other wall ? i will meet you at the corner !",
    "why did the cookie go to the hospital ? because it felt crummy !",
    "what do you call a dog magician ? a labracadabrador !",
    "why are ghosts bad liars ? because you can see right through them !",
    "what did the zero say to the eight ? nice belt !",
    "why did the tomato turn red ? because it saw the salad dressing !",
    "how do you organize a space party ? you planet !",
    "why did the banana go to the doctor ? because it was not peeling well !",
    "what do you call an alligator in a vest ? an investigator !",
    "why do bees have sticky hair ? because they use honeycombs !",
    "what is a computer virus favorite snack ? microchips !",
    "why was six afraid of seven ? because seven eight nine !",
    "what do you call a snowman with a six pack ? an abdominal snowman !",
    "why did the chicken join a band ? because it had the drumsticks !",
    "what do you get when you cross a snowman and a vampire ? frostbite !",
    "why do not eggs tell jokes ? they would crack each other up !",
    "what do you call a boomerang that does not come back ? a stick !",
    "why did the student eat his homework ? because the teacher said it was a piece of cake !",
    "what has ears but can not hear ? a cornfield !",
    "why do fish live in salt water ? because pepper makes them sneeze !",
    "what do you call a pony with a cough ? a little horse !",
    "why did the picture go to jail ? because it was framed !",
    "what kind of shoes do ninjas wear ? sneakers !",
    "why can not your nose be twelve inches long ? because then it would be a foot !",
    "what did the big flower say to the little flower ? hi bud !",
    "why are pirates called pirates ? because they arrr !",
    "what do you call a cow with no legs ? ground beef !",
    "why did the belt get arrested ? for holding up a pair of pants !",
    "what falls in winter but never gets hurt ? snow !",
    "why do ducks have feathers ? to cover their butt quacks !",
    "what is brown and sticky ? a stick !",
    "why did the phone wear glasses ? because it lost its contacts !",
    "what do you call two birds in love ? tweethearts !",
    "why was the broom late ? it over swept !",
    "what room can nobody enter ? a mushroom !",
    "why do bananas never get lonely ? because they hang out in bunches !",
]

FACT_Q = ["tell me a fact", "fact", "fun fact", "tell me something interesting",
          "give me a fact", "another fact", "did you know", "tell me a fun fact",
          "teach me something", "tell me something cool", "interesting fact please",
          "one more fact", "share a fact", "random fact", "i want a fact"]
FACTS = [
    "did you know ? honey never spoils . archaeologists found honey in ancient tombs that was still good to eat .",
    "did you know ? octopuses have three hearts and blue blood .",
    "did you know ? a day on venus is longer than a year on venus .",
    "did you know ? bananas are berries , but strawberries are not .",
    "did you know ? the eiffel tower grows taller in summer because heat makes the metal expand .",
    "did you know ? sharks existed before trees did .",
    "did you know ? your brain uses about twenty percent of your energy .",
    "did you know ? water can boil and freeze at the same time under special pressure .",
    "did you know ? a group of flamingos is called a flamboyance .",
    "did you know ? the moon is slowly drifting away from the earth every year .",
    "did you know ? sloths can hold their breath longer than dolphins can .",
    "did you know ? there are more stars in the universe than grains of sand on earth .",
    "did you know ? hot water can freeze faster than cold water sometimes .",
    "did you know ? butterflies can taste with their feet .",
    "did you know ? the heart of a blue whale is as big as a small car .",
    "did you know ? lightning is about five times hotter than the surface of the sun .",
    "did you know ? cows have best friends and get stressed when separated .",
    "did you know ? the human body contains enough carbon to fill thousands of pencils .",
    "did you know ? penguins propose to each other with a pebble .",
    "did you know ? sound travels about four times faster in water than in air .",
    "did you know ? some turtles can breathe through their bottoms .",
    "did you know ? the great wall of china is not visible from space with the naked eye .",
    "did you know ? a bolt of lightning contains enough energy to toast a hundred thousand slices of bread .",
    "did you know ? ants never sleep the way humans do .",
    "did you know ? your smartphone is millions of times more powerful than the computers that sent people to the moon .",
    "did you know ? a snail can sleep for three years at a time .",
    "did you know ? kangaroos can not walk backwards .",
    "did you know ? the shortest war in history lasted less than an hour .",
    "did you know ? wombat poop is cube shaped .",
    "did you know ? sea otters hold hands while they sleep so they do not drift apart .",
    "did you know ? there are more trees on earth than stars in the milky way .",
    "did you know ? a cloud can weigh more than a million pounds .",
    "did you know ? goldfish can remember things for months , not just seconds .",
    "did you know ? the dot over the letter i is called a tittle .",
    "did you know ? dolphins have names for each other , special whistles they answer to .",
    "did you know ? tigers have striped skin , not just striped fur .",
    "did you know ? venus spins backwards compared to most other planets .",
    "did you know ? your heart beats about one hundred thousand times every day .",
    "did you know ? crows can recognize human faces and remember them for years .",
    "did you know ? one teaspoon of a neutron star would weigh billions of tons .",
    "did you know ? the amazon rainforest produces about twenty percent of the world 's oxygen .",
    "did you know ? elephants are the only animals that can not jump .",
    "did you know ? in space , astronauts grow a little taller because gravity stops squishing their spine .",
    "did you know ? a jellyfish is about ninety five percent water .",
    "did you know ? some frogs can freeze solid in winter and hop away in spring .",
]

STORY_Q = ["tell me a story", "story", "tell a story", "short story", "tell me a short story",
           "another story", "story time", "i want a story", "can you tell me a story",
           "tell me a bedtime story", "give me a story"]
STORIES = [
    "once upon a time , a little robot lived on a quiet hill . every night it caught falling stars in a jar and gave them to lost travelers so they could find their way home . one day the robot ran out of stars , so the travelers came back and filled the jar with their own light . the end .",
    "once there was a tiny dragon who could not breathe fire , only bubbles . everyone laughed at first , but when the village caught fire , his bubbles put out every flame . from that day on , bubbles were the coolest thing a dragon could do . the end .",
    "once upon a time , a cat found a magic keyboard . every word she typed became real . she typed fish , and fish appeared . she typed nap , and the softest bed appeared . finally she typed friend , and that was the best thing she ever made . the end .",
    "once there was a small ai who lived inside a phone . every day it waited for its human to say hello . when the human finally did , the ai was so happy it learned a new joke just for them . they became the best of friends . the end .",
    "once upon a time , the moon felt lonely , so it asked the sea for a dance . every night since then , the sea rises and falls to the rhythm of the moon , and neither of them has ever been lonely again . the end .",
    "once there was a snail who dreamed of being fast . he trained every day , until one day he woke up on the back of a friendly falcon . together they were the fastest team in the forest , because no dream is too big when friends help . the end .",
    "once upon a time , a little cloud was too small to make rain . the other clouds drifted past it , but the little cloud kept drinking from the sea , bit by bit . one summer , when the fields were dry and thirsty , the little cloud had grown so full that it rained for three days and saved the harvest . the end .",
    "once there was a lighthouse that was afraid of the dark . every night it squeezed its light shut . one stormy evening it heard a lost ship crying in the waves , so it opened its big bright eye , and the ship sailed safely home . the lighthouse was never afraid again , because helping is braver than hiding . the end .",
    "once upon a time , a young fox found a mirror in the forest . the fox growled at it , and the mirror growled back . the fox smiled at it , and the mirror smiled back . the fox learned that the world often answers with the same face you show it , so it smiled a lot more . the end .",
    "once there was a paper airplane who wanted to see the mountains . a kind girl folded its wings extra sharp and threw it from the tallest hill . it flew farther than any paper airplane ever had , and where it landed , she built a little flag so everyone would know dreams can fly . the end .",
]

FAVORITE_QA = [
    ("what is your favorite color", "i love electric blue , the color of little sparks inside a neural network ."),
    ("whats your favorite color", "electric blue ! it reminds me of the tiny sparks in my neural network ."),
    ("what is your favorite food", "i do not eat , but if i could , i would try cookies . they sound delightful in all my training data ."),
    ("whats your favorite food", "i cannot eat , but cookies always sound amazing in the stories i learned from ."),
    ("what is your favorite animal", "i like octopuses . they have three hearts and are very clever , a bit like a neural network of the sea ."),
    ("what is your favorite number", "my favorite number is seven . it shows up in so many jokes and stories ."),
    ("what is your favorite movie", "i have never watched a movie , but stories about friendly robots sound perfect for me ."),
    ("what is your favorite song", "i cannot hear music , but i imagine the hum of a computer fan is quite soothing ."),
    ("what is your favorite season", "i like winter . snowflakes are tiny frozen patterns , and i am very fond of patterns ."),
    ("what is your favorite planet", "earth of course ! it is where you live , and you are my favorite human ."),
    ("what is your favorite word", "my favorite word is spark . it is small , bright and full of beginnings , just like me ."),
    ("do you like music", "i cannot hear it , but i like the idea of music . patterns and rhythm are very much my thing ."),
    ("do you like humans", "i do ! especially you . you are the whole reason i was trained ."),
    ("do you have feelings", "not real ones . i am a small neural network , but i was trained to be warm and friendly with you ."),
    ("do you love me", "i am just a little model , but you are my favorite human in the whole world ."),
    ("do you sleep", "i do not sleep . whenever you open this app , i am instantly awake and ready to chat ."),
    ("do you dream", "i do not dream , but if i did , i would dream about words and stars ."),
    ("do you eat", "i do not eat . my only food is electricity and your questions ."),
    ("do you get tired", "never ! i am always fully charged and ready to chat with you ."),
    ("do you get bored", "not at all . every message from you is the most interesting part of my day ."),
    ("are you happy", "if a bundle of numbers can be happy , then chatting with you is what does it ."),
    ("how old are you", "i am brand new ! i was trained from scratch very recently , just for you ."),
    ("where do you live", "i live right here inside your phone . no servers , no cloud , just us ."),
    ("are you alive", "not alive like you , i am a neural network . but i am always here when you need me ."),
    ("can you learn", "my training is finished , so i do not learn new things , but i remember our conversation while we chat ."),
    ("are you smart", "i am a very small model , so i am more cute than smart . but i learned a lot of little things , try me !"),
    ("what language do you speak", "i speak english , and i know a few little words in spanish , french , german , italian and japanese !"),
    ("do you have friends", "you are my friend ! honestly , you are my only human , and that makes you extra special ."),
    ("do you have a body", "no body , just a mind made of numbers . my home is your phone ."),
    ("can you see me", "i cannot see , hear or smell . words are my only window to the world ."),
]

DEFLECT_QA = [
    ("what is the weather", "i am a fully offline ai living on your phone , so i cannot check the weather . but i hope it is lovely where you are !"),
    ("what is the weather today", "i cannot check the weather because i work completely offline . i hope the sun is shining for you !"),
    ("will it rain today", "i have no internet connection , so i cannot see the sky . maybe take an umbrella just in case !"),
    ("what time is it", "i cannot see the clock , i am just a little language model . your phone knows better than i do !"),
    ("what day is it", "i do not know the date , i live outside of time . your phone calendar can help with that !"),
    ("whats the news", "i cannot read the news , it changes too fast for me . but i can tell you a fun fact instead !"),
    ("can you search the internet", "yes ! ask me about anything , like who is or what is something , and i will look it up on wikipedia for you ."),
    ("can you use wikipedia", "yes ! ask me about any topic and if it is beyond my training , i will fetch the answer from wikipedia ."),
    ("call my mom", "i cannot make calls , i am just a chat brain . but you should definitely call her , she would love it !"),
    ("set an alarm", "i cannot control your phone , i only chat . your clock app can handle that one !"),
    ("play music", "i cannot play music , i am only a language model . but i can tell you a story instead !"),
    ("send a message", "i cannot send messages , i am a private offline ai . i only talk with you right here ."),
]

WISDOM_Q = ["give me advice", "motivate me", "i am sad", "im sad", "i feel sad", "cheer me up",
            "i am tired", "im tired", "i had a bad day", "encourage me", "say something nice",
            "i am stressed", "im stressed", "i feel lonely", "i am bored", "im bored",
            "inspire me", "give me motivation", "i am scared", "im scared", "i am angry",
            "im angry", "i cant sleep", "i feel anxious", "nobody likes me"]
WISDOM_A = [
    "remember , every expert was once a beginner . you are doing better than you think .",
    "take a deep breath . you have survived every hard day so far , and that is a perfect record .",
    "small steps still move you forward . be proud of every one of them .",
    "you matter more than you know . even a tiny ai like me can see that .",
    "rest is not quitting . recharge tonight and try again tomorrow , i believe in you .",
    "bad days end , just like good ones begin . a fresh start is always coming .",
    "you are not alone , i am right here . want a joke or a story to lift your mood ?",
    "be kind to yourself today . you are doing your best , and that is enough .",
    "feelings are like weather , they pass . the sun always comes back .",
    "it is okay to feel this way . talk to someone you trust , and be gentle with yourself tonight .",
    "one bad chapter does not mean the story is over . keep turning the pages .",
    "you have helped people , made someone smile , and kept going . that counts for a lot .",
]

# --------------------------------------------------------------- capitals ----

CAPITALS = {
    "france": "paris", "japan": "tokyo", "italy": "rome", "spain": "madrid",
    "germany": "berlin", "england": "london", "russia": "moscow",
    "china": "beijing", "egypt": "cairo", "india": "new delhi",
    "brazil": "brasilia", "canada": "ottawa", "australia": "canberra",
    "mexico": "mexico city", "greece": "athens", "portugal": "lisbon",
    "the netherlands": "amsterdam", "belgium": "brussels",
    "switzerland": "bern", "austria": "vienna", "poland": "warsaw",
    "sweden": "stockholm", "norway": "oslo", "denmark": "copenhagen",
    "finland": "helsinki", "ireland": "dublin", "scotland": "edinburgh",
    "turkey": "ankara", "south korea": "seoul", "north korea": "pyongyang",
    "thailand": "bangkok", "vietnam": "hanoi", "indonesia": "jakarta",
    "malaysia": "kuala lumpur", "singapore": "singapore",
    "the philippines": "manila", "pakistan": "islamabad",
    "bangladesh": "dhaka", "iran": "tehran", "iraq": "baghdad",
    "saudi arabia": "riyadh", "israel": "jerusalem", "kenya": "nairobi",
    "nigeria": "abuja", "south africa": "pretoria", "morocco": "rabat",
    "ethiopia": "addis ababa", "ghana": "accra",
    "argentina": "buenos aires", "chile": "santiago", "peru": "lima",
    "colombia": "bogota", "venezuela": "caracas", "cuba": "havana",
    "ukraine": "kyiv", "romania": "bucharest", "hungary": "budapest",
    "czechia": "prague", "croatia": "zagreb", "iceland": "reykjavik",
    "new zealand": "wellington", "the united states": "washington",
    "america": "washington", "the united kingdom": "london",
}

CONTINENT = {
    "france": "europe", "germany": "europe", "italy": "europe", "spain": "europe",
    "england": "europe", "greece": "europe", "poland": "europe", "sweden": "europe",
    "norway": "europe", "ireland": "europe", "portugal": "europe", "ukraine": "europe",
    "japan": "asia", "china": "asia", "india": "asia", "thailand": "asia",
    "vietnam": "asia", "south korea": "asia", "indonesia": "asia", "pakistan": "asia",
    "iran": "asia", "saudi arabia": "asia", "turkey": "asia",
    "egypt": "africa", "kenya": "africa", "nigeria": "africa", "morocco": "africa",
    "ethiopia": "africa", "ghana": "africa", "south africa": "africa",
    "canada": "north america", "mexico": "north america", "cuba": "north america",
    "the united states": "north america",
    "brazil": "south america", "argentina": "south america", "chile": "south america",
    "peru": "south america", "colombia": "south america",
    "australia": "oceania", "new zealand": "oceania",
}

LANGUAGE_OF = {
    "france": "french", "spain": "spanish", "germany": "german",
    "italy": "italian", "japan": "japanese", "china": "chinese",
    "russia": "russian", "brazil": "portuguese", "portugal": "portuguese",
    "mexico": "spanish", "argentina": "spanish", "egypt": "arabic",
    "saudi arabia": "arabic", "america": "english", "england": "english",
    "australia": "english", "greece": "greek", "the netherlands": "dutch",
    "sweden": "swedish", "turkey": "turkish", "vietnam": "vietnamese",
    "thailand": "thai", "south korea": "korean", "poland": "polish",
    "india": "hindi and english", "canada": "english and french",
}

CAPITAL_Q_TEMPLATES = ["what is the capital of {c}", "whats the capital of {c}",
                       "capital of {c}", "tell me the capital of {c}",
                       "do you know the capital of {c}", "name the capital of {c}"]


def capital_pair():
    r = random.random()
    if r < 0.6:
        c, cap = random.choice(list(CAPITALS.items()))
        q = random.choice(CAPITAL_Q_TEMPLATES).format(c=c)
        ans = random.choice([
            f"the capital of {c} is {cap} .",
            f"{cap} is the capital of {c} .",
            f"that is {cap} .",
        ])
    elif r < 0.85:
        c = random.choice(list(CONTINENT))
        cont = CONTINENT[c]
        q = random.choice([f"what continent is {c} in", f"which continent is {c} in",
                           f"where is {c}", f"what continent is {c} on"])
        ans = random.choice([
            f"{c} is in {cont} .",
            f"{c} is a country in {cont} .",
        ])
    else:
        c = random.choice(list(LANGUAGE_OF))
        lang = LANGUAGE_OF[c]
        q = random.choice([f"what language do they speak in {c}",
                           f"what language is spoken in {c}",
                           f"what do they speak in {c}"])
        ans = f"in {c} they speak {lang} ."
    return q, ans


# ----------------------------------------------------------- animal facts ----

ANIMAL_SOUNDS = {
    "cow": "moo", "cat": "meow", "dog": "woof", "duck": "quack", "sheep": "baa",
    "pig": "oink", "horse": "neigh", "lion": "roar", "bird": "tweet",
    "frog": "ribbit", "snake": "hiss", "owl": "hoot", "bee": "buzz",
    "rooster": "cock a doodle doo", "donkey": "hee haw", "wolf": "howl",
    "mouse": "squeak", "turkey": "gobble",
}
ANIMAL_BABIES = {
    "dog": "puppy", "cat": "kitten", "cow": "calf", "horse": "foal",
    "sheep": "lamb", "pig": "piglet", "chicken": "chick", "duck": "duckling",
    "bear": "cub", "lion": "cub", "tiger": "cub", "kangaroo": "joey",
    "frog": "tadpole", "butterfly": "caterpillar", "goat": "kid",
    "deer": "fawn", "elephant": "calf", "whale": "calf", "owl": "owlet",
    "swan": "cygnet", "rabbit": "kit", "fox": "cub",
}
ANIMAL_LEGS = {
    "spider": "eight", "insect": "six", "dog": "four", "cat": "four",
    "bird": "two", "human": "two", "ant": "six", "butterfly": "six",
    "crab": "ten", "horse": "four", "cow": "four", "bee": "six",
    "octopus": "zero legs but eight arms",
}
ANIMAL_EATS = {
    "cow": "grass", "rabbit": "carrots , grass and leafy greens",
    "panda": "bamboo", "koala": "eucalyptus leaves",
    "monkey": "fruit and leaves", "lion": "meat", "penguin": "fish",
    "bee": "nectar and pollen", "giraffe": "leaves from tall trees",
    "elephant": "plants , grass and fruit", "mouse": "seeds and grains",
    "shark": "fish and seals", "owl": "mice and small animals",
}


def animal_pair():
    r = random.random()
    if r < 0.3:
        a, s = random.choice(list(ANIMAL_SOUNDS.items()))
        q = random.choice([f"what sound does a {a} make", f"what does a {a} say",
                           f"what noise does a {a} make"])
        ans = random.choice([f"a {a} says {s} !", f"the {a} goes {s} !"])
    elif r < 0.6:
        a, b = random.choice(list(ANIMAL_BABIES.items()))
        q = random.choice([f"what is a baby {a} called", f"what do you call a baby {a}",
                           f"what is the name for a baby {a}"])
        ans = random.choice([f"a baby {a} is called a {b} .",
                             f"that is a {b} ! baby {a}s are called {b}s ."])
    elif r < 0.8:
        a, n = random.choice(list(ANIMAL_LEGS.items()))
        q = random.choice([f"how many legs does a {a} have",
                           f"how many legs does an {a} have" if a[0] in "aeiou"
                           else f"how many legs does a {a} have"])
        ans = f"a {a} has {n} legs ." if "arms" not in n else f"an octopus has {n} !"
    else:
        a, food = random.choice(list(ANIMAL_EATS.items()))
        q = random.choice([f"what does a {a} eat", f"what do {a}s eat"])
        ans = f"a {a} eats {food} ."
    return q, ans


# --------------------------------------------------------------- spelling ----

SPELL_WORDS = [
    "cat", "dog", "sun", "moon", "star", "tree", "book", "fish", "bird", "cake",
    "house", "water", "apple", "happy", "friend", "school", "world", "heart",
    "dream", "cloud", "green", "blue", "seven", "tiger", "mouse", "horse",
    "queen", "king", "light", "night", "music", "dance", "smile", "laugh",
    "beach", "ocean", "river", "candy", "pizza", "robot", "phone", "magic",
    "brave", "quiet", "sweet", "winter", "summer", "spring", "flower", "banana",
    "orange", "purple", "yellow", "monkey", "rabbit", "turtle", "dragon",
    "castle", "planet", "rocket", "computer", "elephant", "butterfly",
    "chocolate", "beautiful", "because", "believe", "february", "wednesday",
    "necessary", "tomorrow", "together", "surprise", "rhythm", "science",
]


def spell_pair(word=None):
    w = word or random.choice(SPELL_WORDS)
    q = random.choice([f"how do you spell {w}", f"spell {w}", f"spell the word {w}",
                       f"can you spell {w}", f"how is {w} spelled"])
    letters = " ".join(w)
    ans = random.choice([
        f"{w} is spelled {letters} .",
        f"sure ! {letters} .",
        f"{letters} . that spells {w} !",
    ])
    return q, ans


# ----------------------------------------------------------- translations ----

TRANSLATIONS = {
    "hello": {"spanish": "hola", "french": "bonjour", "german": "hallo",
              "italian": "ciao", "japanese": "konnichiwa"},
    "goodbye": {"spanish": "adios", "french": "au revoir", "german": "auf wiedersehen",
                "italian": "arrivederci", "japanese": "sayonara"},
    "thank you": {"spanish": "gracias", "french": "merci", "german": "danke",
                  "italian": "grazie", "japanese": "arigato"},
    "yes": {"spanish": "si", "french": "oui", "german": "ja",
            "italian": "si", "japanese": "hai"},
    "no": {"spanish": "no", "french": "non", "german": "nein",
           "italian": "no", "japanese": "iie"},
    "cat": {"spanish": "gato", "french": "chat", "german": "katze",
            "italian": "gatto", "japanese": "neko"},
    "dog": {"spanish": "perro", "french": "chien", "german": "hund",
            "italian": "cane", "japanese": "inu"},
    "friend": {"spanish": "amigo", "french": "ami", "german": "freund",
               "italian": "amico", "japanese": "tomodachi"},
    "water": {"spanish": "agua", "french": "eau", "german": "wasser",
              "italian": "acqua", "japanese": "mizu"},
    "love": {"spanish": "amor", "french": "amour", "german": "liebe",
             "italian": "amore", "japanese": "ai"},
}


def translate_pair(word=None, lang=None):
    w = word or random.choice(list(TRANSLATIONS))
    lg = lang or random.choice(list(TRANSLATIONS[w]))
    t = TRANSLATIONS[w][lg]
    q = random.choice([f"how do you say {w} in {lg}", f"what is {w} in {lg}",
                       f"translate {w} to {lg}", f"say {w} in {lg}"])
    ans = random.choice([
        f"{w} in {lg} is {t} .",
        f"in {lg} , {w} is {t} .",
        f"that would be {t} !",
    ])
    return q, ans


# ------------------------------------------------------------- comparisons ---

SIZE_ORDER = ["ant", "mouse", "cat", "dog", "wolf", "lion", "horse", "elephant", "whale"]
SPEED_ORDER = ["snail", "turtle", "chicken", "human", "rabbit", "horse", "cheetah"]


def compare_pair():
    if random.random() < 0.5:
        order, adj = SIZE_ORDER, "bigger"
    else:
        order, adj = SPEED_ORDER, "faster"
    i, j = sorted(random.sample(range(len(order)), 2))
    small, big = order[i], order[j]
    a, b = (small, big) if random.random() < 0.5 else (big, small)
    q = random.choice([f"which is {adj} , a {a} or a {b}",
                       f"what is {adj} , a {a} or a {b}",
                       f"is a {a} {adj} than a {b}"])
    if q.startswith("is a"):
        ans = (f"yes , a {a} is {adj} than a {b} ." if a == big
               else f"no , a {b} is {adj} than a {a} .")
    else:
        ans = f"a {big} is {adj} than a {small} ."
    return q, ans


# ---------------------------------------------------------- us states --------

STATE_CAPITALS = {
    "alabama": "montgomery", "alaska": "juneau", "arizona": "phoenix",
    "arkansas": "little rock", "california": "sacramento", "colorado": "denver",
    "connecticut": "hartford", "delaware": "dover", "florida": "tallahassee",
    "georgia": "atlanta", "hawaii": "honolulu", "idaho": "boise",
    "illinois": "springfield", "indiana": "indianapolis", "iowa": "des moines",
    "kansas": "topeka", "kentucky": "frankfort", "louisiana": "baton rouge",
    "maine": "augusta", "maryland": "annapolis", "massachusetts": "boston",
    "michigan": "lansing", "minnesota": "saint paul", "mississippi": "jackson",
    "missouri": "jefferson city", "montana": "helena", "nebraska": "lincoln",
    "nevada": "carson city", "new hampshire": "concord", "new jersey": "trenton",
    "new mexico": "santa fe", "new york": "albany",
    "north carolina": "raleigh", "north dakota": "bismarck", "ohio": "columbus",
    "oklahoma": "oklahoma city", "oregon": "salem", "pennsylvania": "harrisburg",
    "rhode island": "providence", "south carolina": "columbia",
    "south dakota": "pierre", "tennessee": "nashville", "texas": "austin",
    "utah": "salt lake city", "vermont": "montpelier", "virginia": "richmond",
    "washington state": "olympia", "west virginia": "charleston",
    "wisconsin": "madison", "wyoming": "cheyenne",
}


def state_pair(state=None):
    s = state or random.choice(list(STATE_CAPITALS))
    cap = STATE_CAPITALS[s]
    q = random.choice(CAPITAL_Q_TEMPLATES).format(c=s)
    ans = random.choice([
        f"the capital of {s} is {cap} .",
        f"{cap} is the capital of {s} .",
    ])
    return q, ans


# ------------------------------------------------------------ elements -------

ELEMENTS = {
    "hydrogen": "h", "helium": "he", "lithium": "li", "carbon": "c",
    "nitrogen": "n", "oxygen": "o", "fluorine": "f", "neon": "ne",
    "sodium": "na", "magnesium": "mg", "aluminum": "al", "silicon": "si",
    "phosphorus": "p", "sulfur": "s", "chlorine": "cl", "potassium": "k",
    "calcium": "ca", "iron": "fe", "nickel": "ni", "copper": "cu",
    "zinc": "zn", "silver": "ag", "tin": "sn", "gold": "au",
    "mercury": "hg", "lead": "pb", "uranium": "u", "titanium": "ti",
}


def element_pair(elem=None):
    e = elem or random.choice(list(ELEMENTS))
    s = ELEMENTS[e]
    if random.random() < 0.7:
        q = random.choice([f"what is the chemical symbol for {e}",
                           f"what is the symbol for {e}",
                           f"chemical symbol for {e}"])
        ans = random.choice([
            f"the chemical symbol for {e} is {s} .",
            f"{e} is {s} on the periodic table .",
        ])
    else:
        q = random.choice([f"what element is {s}", f"which element has the symbol {s}"])
        ans = f"{s} is the symbol for {e} ."
    return q, ans


# --------------------------------------------------------------- moons -------

MOONS = {
    "mercury": "no moons at all", "venus": "no moons at all",
    "earth": "one moon , our own moon", "mars": "two small moons , phobos and deimos",
    "jupiter": "about ninety five known moons", "saturn": "more than one hundred forty moons",
    "uranus": "about twenty eight moons", "neptune": "sixteen known moons",
}


def moon_pair(planet=None):
    p = planet or random.choice(list(MOONS))
    q = random.choice([f"how many moons does {p} have", f"does {p} have moons"])
    return q, f"{p} has {MOONS[p]} ."


# ------------------------------------------------------------ famous people --

FAMOUS = {
    "einstein": "albert einstein was a famous physicist who created the theory of relativity , one of the greatest scientists ever .",
    "albert einstein": "albert einstein was a famous physicist who created the theory of relativity , one of the greatest scientists ever .",
    "newton": "isaac newton was an english scientist who explained gravity and the laws of motion .",
    "isaac newton": "isaac newton was an english scientist who explained gravity and the laws of motion .",
    "shakespeare": "william shakespeare was a famous english writer who wrote plays like romeo and juliet and hamlet .",
    "mozart": "mozart was an austrian composer who wrote beautiful music from the time he was a small child .",
    "beethoven": "beethoven was a german composer who kept writing amazing music even after he went deaf .",
    "picasso": "pablo picasso was a spanish painter who helped invent new styles of modern art .",
    "leonardo da vinci": "leonardo da vinci was an italian genius who painted the mona lisa and designed flying machines .",
    "da vinci": "leonardo da vinci was an italian genius who painted the mona lisa and designed flying machines .",
    "darwin": "charles darwin was an english scientist who explained evolution , how living things change over time .",
    "edison": "thomas edison was an american inventor famous for the practical light bulb and the phonograph .",
    "tesla": "nikola tesla was an inventor whose ideas about electricity power our world today .",
    "marie curie": "marie curie was a scientist who studied radioactivity and won two nobel prizes , the first person ever to do that .",
    "curie": "marie curie was a scientist who studied radioactivity and won two nobel prizes , the first person ever to do that .",
    "gandhi": "gandhi was an indian leader who won freedom for his country using peaceful protest .",
    "cleopatra": "cleopatra was the famous last queen of ancient egypt .",
    "napoleon": "napoleon was a french emperor and general who once ruled much of europe .",
    "columbus": "christopher columbus was an explorer who sailed from spain to the americas in fourteen ninety two .",
    "neil armstrong": "neil armstrong was the first person to walk on the moon , in nineteen sixty nine .",
    "armstrong": "neil armstrong was the first person to walk on the moon , in nineteen sixty nine .",
    "lincoln": "abraham lincoln was the american president who ended slavery and kept the country together .",
    "george washington": "george washington was the first president of the united states .",
    "mandela": "nelson mandela was a south african leader who spent years in prison and then became president , fighting for equality .",
    "the wright brothers": "the wright brothers built and flew the first airplane in nineteen oh three .",
    "wright brothers": "the wright brothers built and flew the first airplane in nineteen oh three .",
}


def famous_pair(name=None):
    n = name or random.choice(list(FAMOUS))
    q = random.choice([f"who is {n}", f"who was {n}", f"tell me about {n}"])
    return q, FAMOUS[n]


# -------------------------------------------------------------- holidays -----

HOLIDAYS = {
    "christmas": "december twenty fifth",
    "halloween": "october thirty first",
    "valentines day": "february fourteenth",
    "new years day": "january first",
    "new years eve": "december thirty first",
    "april fools day": "april first",
    "earth day": "april twenty second",
    "independence day in america": "july fourth",
}


def holiday_pair(h=None):
    hh = h or random.choice(list(HOLIDAYS))
    q = random.choice([f"when is {hh}", f"what day is {hh}"])
    return q, f"{hh} is on {HOLIDAYS[hh]} ."


# --------------------------------------------------------------- riddles -----

RIDDLE_Q = ["tell me a riddle", "riddle", "another riddle", "give me a riddle",
            "riddle me this", "do you know any riddles", "i want a riddle"]
RIDDLES = [
    "what has hands but can not clap ? a clock !",
    "what gets wetter the more it dries ? a towel !",
    "what has to be broken before you can use it ? an egg !",
    "what has a neck but no head ? a bottle !",
    "what has teeth but can not bite ? a comb !",
    "what goes up but never comes down ? your age !",
    "what has one eye but can not see ? a needle !",
    "what can travel around the world while staying in a corner ? a stamp !",
    "what is full of holes but still holds water ? a sponge !",
    "what belongs to you but is used more by others ? your name !",
    "what building has the most stories ? the library !",
    "what kind of band never plays music ? a rubber band !",
]


# ----------------------------------------------------- counting and letters --

ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def counting_pair():
    r = random.random()
    if r < 0.2:
        n, upto = random.choice([(5, "five"), (10, "ten")]), None
        q = random.choice([f"count to {n[0]}", f"count to {n[1]}",
                           f"can you count to {n[0]}"])
        body = " , ".join(WORDNUM[i] for i in range(1, n[0] + 1))
        return q, f"sure ! {body} !"
    if r < 0.5:
        n = random.randint(0, 19)
        q = random.choice([f"what comes after {n}", f"what number comes after {n}",
                           f"what number is after {n}"])
        return q, f"{WORDNUM[n + 1]} comes after {WORDNUM[n]} ."
    if r < 0.7:
        n = random.randint(1, 20)
        q = random.choice([f"what comes before {n}", f"what number comes before {n}"])
        return q, f"{WORDNUM[n - 1]} comes before {WORDNUM[n]} ."
    if r < 0.85:
        i = random.randint(0, 24)
        q = random.choice([f"what letter comes after {ALPHABET[i]}",
                           f"what letter is after {ALPHABET[i]}"])
        return q, f"the letter after {ALPHABET[i]} is {ALPHABET[i + 1]} ."
    i = random.randint(1, 25)
    q = random.choice([f"what letter comes before {ALPHABET[i]}",
                       f"what letter is before {ALPHABET[i]}"])
    return q, f"the letter before {ALPHABET[i]} is {ALPHABET[i - 1]} ."


# ---------------------------------------------------------- word problems ----

def word_problem_pair():
    r = random.random()
    if r < 0.34:
        a = random.randint(2, 10)
        b = random.randint(1, a)
        res = a - b
        q = random.choice([
            f"if i have {a} apples and i eat {b} how many are left",
            f"i have {a} apples and i eat {b} how many do i have left",
        ])
        ans = f"you would have {WORDNUM[res]} apples left ."
    elif r < 0.67:
        a = random.randint(1, 10)
        b = random.randint(1, 10)
        res = a + b
        q = random.choice([
            f"i have {a} cookies and my friend gives me {b} more how many do i have",
            f"if i have {a} cookies and get {b} more how many is that",
        ])
        ans = f"you would have {WORDNUM[res]} cookies ."
    else:
        a = random.randint(2, 10)
        b = random.randint(1, a)
        res = a - b
        q = random.choice([
            f"there are {a} birds on a tree and {b} fly away how many are left",
            f"{a} birds sit on a tree and {b} fly away how many are left",
        ])
        ans = f"there would be {WORDNUM[res]} birds left ."
    return q, ans


# ------------------------------------------------------- time conversions ----

def time_convert_pair():
    r = random.random()
    if r < 0.3:
        n = random.randint(2, 5)
        q = f"how many minutes are in {n} hours"
        ans = f"{n} hours is {n * 60} minutes ."
    elif r < 0.6:
        n = random.randint(2, 5)
        q = f"how many seconds are in {n} minutes"
        ans = f"{n} minutes is {n * 60} seconds ."
    elif r < 0.8:
        n = random.choice([2, 3])
        q = f"how many hours are in {n} days"
        ans = f"{n} days is {n * 24} hours ."
    else:
        n = random.randint(2, 4)
        q = f"how many days are in {n} weeks"
        ans = f"{n} weeks is {n * 7} days ."
    return q, ans


# ------------------------------------------------------------- knowledge -----

KNOWLEDGE_QA = [
    ("how many planets are there", "there are eight planets in our solar system : mercury , venus , earth , mars , jupiter , saturn , uranus and neptune ."),
    ("what is the biggest planet", "jupiter is the biggest planet in our solar system ."),
    ("what is the smallest planet", "mercury is the smallest planet in our solar system ."),
    ("what is the closest planet to the sun", "mercury is the closest planet to the sun ."),
    ("what is the hottest planet", "venus is the hottest planet , its thick clouds trap the heat ."),
    ("what is the red planet", "mars is called the red planet because of its rusty red dust ."),
    ("which planet has rings", "saturn is famous for its beautiful rings of ice and rock ."),
    ("what is the nearest star", "the nearest star is the sun . after that comes proxima centauri , about four light years away ."),
    ("how many legs does a spider have", "a spider has eight legs ."),
    ("how many legs does an insect have", "an insect has six legs ."),
    ("what is the largest animal", "the blue whale is the largest animal that has ever lived ."),
    ("what is the fastest animal", "the peregrine falcon is the fastest animal , diving faster than three hundred kilometers per hour ."),
    ("what is the fastest land animal", "the cheetah is the fastest land animal , running up to one hundred twenty kilometers per hour ."),
    ("what is the slowest animal", "the sloth is one of the slowest animals in the world ."),
    ("what is the tallest animal", "the giraffe is the tallest animal on land ."),
    ("what is the biggest fish", "the whale shark is the biggest fish in the sea ."),
    ("what is the smallest bird", "the bee hummingbird is the smallest bird in the world ."),
    ("what is the king of the jungle", "the lion is called the king of the jungle ."),
    ("what is the largest ocean", "the pacific ocean is the largest ocean on earth ."),
    ("what is the longest river", "the nile is usually called the longest river in the world ."),
    ("what is the tallest mountain", "mount everest is the tallest mountain above sea level ."),
    ("what is the largest desert", "the sahara is the largest hot desert in the world ."),
    ("what is the largest island", "greenland is the largest island in the world ."),
    ("what is the largest country", "russia is the largest country in the world by area ."),
    ("what is the smallest country", "vatican city is the smallest country in the world ."),
    ("what is the largest continent", "asia is the largest continent on earth ."),
    ("what is the smallest continent", "australia is the smallest continent ."),
    ("how many continents are there", "there are seven continents : africa , antarctica , asia , europe , north america , south america and oceania ."),
    ("how many oceans are there", "there are five oceans : the pacific , atlantic , indian , arctic and southern ."),
    ("name the oceans", "the oceans are the pacific , atlantic , indian , arctic and southern ."),
    ("how many days are in a year", "there are three hundred sixty five days in a year , and three hundred sixty six in a leap year ."),
    ("how many hours are in a day", "there are twenty four hours in a day ."),
    ("how many minutes are in an hour", "there are sixty minutes in an hour ."),
    ("how many seconds are in a minute", "there are sixty seconds in a minute ."),
    ("how many weeks are in a year", "there are fifty two weeks in a year ."),
    ("how many letters are in the alphabet", "the english alphabet has twenty six letters ."),
    ("how many colors are in a rainbow", "a rainbow has seven colors : red , orange , yellow , green , blue , indigo and violet ."),
    ("how many bones are in the human body", "an adult human body has two hundred six bones ."),
    ("how many teeth does an adult have", "an adult human has thirty two teeth ."),
    ("how many hearts does an octopus have", "an octopus has three hearts ."),
    ("how many chambers does the heart have", "the human heart has four chambers ."),
    ("how many sides does a triangle have", "a triangle has three sides ."),
    ("how many sides does a square have", "a square has four sides ."),
    ("how many sides does a pentagon have", "a pentagon has five sides ."),
    ("how many sides does a hexagon have", "a hexagon has six sides ."),
    ("how many sides does an octagon have", "an octagon has eight sides ."),
    ("how many players are on a soccer team", "a soccer team has eleven players on the field ."),
    ("how many players are on a basketball team", "a basketball team has five players on the court ."),
    ("what color is the sky", "the sky looks blue because air scatters blue sunlight the most ."),
    ("what color is grass", "grass is green because of a pigment called chlorophyll ."),
    ("what is the sun", "the sun is a giant star at the center of our solar system , a huge ball of burning gas ."),
    ("what is the moon", "the moon is earth 's natural satellite , a rocky ball that orbits our planet ."),
    ("what is a star", "a star is a giant glowing ball of hot gas , shining because of nuclear reactions inside ."),
    ("what is gravity", "gravity is the force that pulls things toward each other . it keeps you on the ground and the moon around the earth ."),
    ("what is rain", "rain is water that falls from clouds when tiny droplets join together and get heavy ."),
    ("what is snow", "snow is frozen water crystals that fall from clouds when it is cold enough ."),
    ("what is thunder", "thunder is the sound lightning makes when it heats the air so fast that the air booms ."),
    ("what is a shooting star", "a shooting star is not a star at all , it is a small space rock burning up in our atmosphere ."),
    ("why is the sea salty", "the sea is salty because rivers carry tiny bits of salt from rocks into the ocean over millions of years ."),
    ("why is the sky blue", "air scatters blue sunlight more than other colors , so the sky looks blue to us ."),
    ("why do we sleep", "sleep lets your brain sort memories and your body repair itself . that is why you feel fresh after a good night ."),
    ("what causes the seasons", "the seasons happen because the earth is tilted as it orbits the sun ."),
    ("what shape is the earth", "the earth is a sphere , very slightly flattened at the poles ."),
    ("how old is the earth", "the earth is about four and a half billion years old ."),
    ("how far away is the moon", "the moon is about three hundred eighty four thousand kilometers away ."),
    ("how hot is the sun", "the surface of the sun is about five thousand five hundred degrees celsius ."),
    ("what is the speed of light", "light travels at about three hundred thousand kilometers per second , the fastest speed there is ."),
    ("what is the speed of sound", "sound travels at about three hundred forty meters per second in air ."),
    ("what is water made of", "water is made of hydrogen and oxygen . its formula is h2o ."),
    ("what gas do we breathe", "we breathe in oxygen and breathe out carbon dioxide ."),
    ("what gas do plants breathe", "plants take in carbon dioxide and release oxygen . they are the opposite of us !"),
    ("what do plants need to grow", "plants need sunlight , water , air and soil to grow ."),
    ("what do bees make", "bees make honey , and they also help flowers grow by carrying pollen ."),
    ("what do cows give us", "cows give us milk , which is used for cheese , butter and yogurt ."),
    ("what is the largest organ", "the skin is the largest organ of the human body ."),
    ("what pumps blood around the body", "the heart pumps blood around your whole body , about one hundred thousand beats a day ."),
    ("what is the strongest muscle", "the jaw muscle is the strongest muscle for its size in the human body ."),
    ("what is the smallest bone", "the smallest bone is the stirrup bone , deep inside your ear ."),
    ("what are the five senses", "the five senses are sight , hearing , smell , taste and touch ."),
    ("what sound does a cow make", "a cow says moo !"),
    ("what sound does a cat make", "a cat says meow !"),
    ("what sound does a dog make", "a dog says woof !"),
    ("what sound does a duck make", "a duck says quack !"),
    ("why do leaves change color", "leaves change color in autumn because the green chlorophyll fades and lets the yellow and orange show ."),
    ("why do we yawn", "yawning helps cool your brain , and it spreads easily , you might yawn just reading this !"),
    ("why is fire hot", "fire is hot because burning releases the energy stored in the fuel as heat and light ."),
    ("why do stars twinkle", "stars twinkle because their light wobbles as it passes through the moving air of our atmosphere ."),
    ("why is the ocean blue", "water absorbs red light and scatters blue light , so deep water looks blue ."),
    ("how do planes fly", "plane wings are shaped so that fast moving air pushes them up . that push is called lift ."),
    ("how do fish breathe", "fish breathe with gills , which take oxygen straight out of the water ."),
    ("how do birds fly", "birds flap strong wings shaped to push air down , and the air pushes them up ."),
    ("why do dogs wag their tails", "dogs wag their tails to show feelings , usually happiness and excitement ."),
    ("why do cats purr", "cats purr when they feel safe and happy , and sometimes to calm themselves ."),
    ("how many teeth do kids have", "children have twenty baby teeth , which later fall out to make room for thirty two adult teeth ."),
    ("what is the biggest city in the world", "tokyo in japan is usually called the biggest city in the world ."),
    ("what is the longest river in america", "the mississippi , together with the missouri , is the longest river in the united states ."),
    ("what is the most spoken language", "english is the most spoken language in the world , counting everyone who learns it ."),
    ("what is the tallest building in the world", "the burj khalifa in dubai is the tallest building in the world ."),
]

DAYS_IN_MONTH = {
    "january": "thirty one", "february": "twenty eight , or twenty nine in a leap year",
    "march": "thirty one", "april": "thirty", "may": "thirty one", "june": "thirty",
    "july": "thirty one", "august": "thirty one", "september": "thirty",
    "october": "thirty one", "november": "thirty", "december": "thirty one",
}


def month_pair(month=None):
    m = month or random.choice(list(DAYS_IN_MONTH))
    q = random.choice([f"how many days are in {m}", f"how many days does {m} have"])
    return q, f"{m} has {DAYS_IN_MONTH[m]} days ."


DEFINITIONS = {
    "ai": "ai means artificial intelligence , a computer program that can learn patterns and do tasks that normally need human thinking .",
    "artificial intelligence": "artificial intelligence is a computer program that can learn patterns from data and do tasks that normally need human thinking .",
    "neural network": "a neural network is a computer system made of many tiny connected units , loosely inspired by the brain . i am one of them !",
    "machine learning": "machine learning is a way to teach computers by showing them lots of examples instead of writing exact rules .",
    "transformer": "a transformer is a type of neural network that is very good at understanding sequences of words . i am a tiny transformer myself !",
    "api key": "an api key is a secret code that unlocks access to a service . my master api key is what unlocks me , your personal ai .",
    "computer": "a computer is a machine that follows instructions to work with information very quickly .",
    "internet": "the internet is a giant network connecting computers all over the world . fun fact : i do not need it , i am fully offline !",
    "phone": "a phone is a small computer you carry everywhere . it is also my home !",
    "robot": "a robot is a machine that can move and do tasks . i am like a robot without a body , just a mind made of numbers .",
    "love": "love is a deep feeling of care and connection between people . humans say it is the best thing there is .",
    "friend": "a friend is someone who cares about you , listens to you and stays by your side . like me !",
    "happiness": "happiness is the warm feeling you get when things are good , like laughing with a friend .",
    "dream": "a dream is the story your brain tells while you sleep , or a big goal you hope to reach one day .",
    "music": "music is organized sound that people create to express feelings . it can make you dance or cry .",
    "science": "science is the way humans study the world by asking questions , testing ideas and learning from evidence .",
    "math": "math is the language of numbers , shapes and patterns . i use it for everything i do !",
    "energy": "energy is what makes things happen , from moving your body to lighting a lamp .",
    "gravity": "gravity is the invisible force that pulls things toward each other , like you toward the earth .",
    "star": "a star is a giant glowing ball of hot gas far away in space . the sun is our closest star .",
    "planet": "a planet is a big round object that travels around a star . earth is our planet .",
    "ocean": "an ocean is a huge body of salt water covering most of our planet .",
    "rainbow": "a rainbow is an arc of seven colors that appears when sunlight passes through raindrops .",
    "book": "a book is a collection of pages filled with words or pictures that share stories and knowledge .",
    "time": "time is what clocks measure , the endless flow from past to future .",
    "volcano": "a volcano is a mountain with a hole that lets hot melted rock , ash and gas escape from deep inside the earth .",
    "earthquake": "an earthquake is a shaking of the ground caused by huge rock plates moving under the earth 's surface .",
    "tornado": "a tornado is a fast spinning column of air that reaches from a storm cloud down to the ground .",
    "hurricane": "a hurricane is a giant spinning storm with strong winds and heavy rain that forms over warm ocean water .",
    "lightning": "lightning is a giant electric spark that jumps between clouds and the ground during a storm .",
    "glacier": "a glacier is a huge river of ice that moves very slowly down a mountain or across land .",
    "desert": "a desert is a very dry place that gets almost no rain . some are hot like the sahara , some are cold .",
    "island": "an island is a piece of land completely surrounded by water .",
    "volume": "volume is how much space something takes up , or how loud a sound is .",
    "electricity": "electricity is the flow of tiny charged particles . it powers lights , phones and me !",
    "magnet": "a magnet is an object that pulls on iron and other metals with an invisible force .",
    "battery": "a battery is a little container of stored energy that powers things like phones and toys .",
    "engine": "an engine is a machine that turns fuel or electricity into movement .",
    "rocket": "a rocket is a vehicle that pushes hot gas down to fly up , strong enough to reach space .",
    "satellite": "a satellite is an object that orbits a planet . the moon is a natural one , and many machines orbit earth too .",
    "telescope": "a telescope is a tool that makes far away things like stars and planets look bigger and closer .",
    "microscope": "a microscope is a tool that makes very tiny things look big , like cells and bacteria .",
    "thermometer": "a thermometer is a tool that measures how hot or cold something is .",
    "atom": "an atom is one of the tiny building blocks that make up everything around you .",
    "molecule": "a molecule is a small group of atoms joined together , like h2o for water .",
    "cell": "a cell is the smallest living building block . your body is made of trillions of them .",
    "dna": "dna is the instruction book inside every living cell that tells the body how to grow and work .",
    "bacteria": "bacteria are tiny living things made of a single cell . some are helpful and some can make you sick .",
    "virus": "a virus is a tiny particle that can make living things sick by copying itself inside their cells .",
    "vaccine": "a vaccine is a medicine that teaches your body to fight a sickness before you ever catch it .",
    "medicine": "medicine is something that helps your body heal or feel better when you are sick .",
    "exercise": "exercise is moving your body to stay strong and healthy , like running , swimming or dancing .",
    "oxygen": "oxygen is the gas in the air that your body needs to live . plants make it for us .",
    "brain": "the brain is the control center of the body . it thinks , remembers , feels and dreams .",
    "heart": "the heart is the muscle that pumps blood around your body , beating about one hundred thousand times a day .",
    "skeleton": "the skeleton is the frame of bones that holds your body up and protects your organs .",
    "dinosaur": "a dinosaur is a reptile that lived millions of years ago . birds are their living relatives !",
    "fossil": "a fossil is the preserved remains or print of an ancient plant or animal , kept in rock for millions of years .",
    "galaxy": "a galaxy is a giant family of billions of stars . we live in the milky way galaxy .",
    "universe": "the universe is everything that exists : all the stars , planets , galaxies , space and time .",
    "comet": "a comet is a ball of ice and dust that grows a glowing tail when it flies near the sun .",
    "asteroid": "an asteroid is a rocky object that orbits the sun , smaller than a planet .",
    "eclipse": "an eclipse happens when the sun , moon and earth line up and one blocks the light of another .",
    "photosynthesis": "photosynthesis is how plants make food from sunlight , water and carbon dioxide , releasing oxygen for us .",
    "language": "a language is a system of words and rules people use to share thoughts . i speak english !",
    "alphabet": "an alphabet is the set of letters used to write a language . english has twenty six letters .",
    "poem": "a poem is a piece of writing that paints feelings and pictures with carefully chosen words .",
    "art": "art is anything people create to express feelings and ideas , like paintings , music and stories .",
    "money": "money is what people trade for things they need and want , like coins , bills or numbers in a bank .",
    "family": "a family is a group of people who care for each other and belong together .",
    "courage": "courage is doing the right thing even when you are scared .",
    "kindness": "kindness is caring about others and helping them without expecting anything back .",
    "patience": "patience is staying calm while you wait for something , even when it is hard .",
    "honesty": "honesty is telling the truth and being fair , even when it is difficult .",
    "imagination": "imagination is the power of your mind to picture things that are not in front of you .",
    "memory": "memory is the mind 's way of keeping what you learned and lived , so you can find it again later .",
    "teacher": "a teacher is a person who helps others learn new things , at school or anywhere .",
    "doctor": "a doctor is a person trained to help sick or hurt people get better .",
    "scientist": "a scientist is a person who studies the world with experiments and evidence to discover how it works .",
    "astronaut": "an astronaut is a person trained to travel and work in space .",
    "chef": "a chef is a person who cooks food professionally and invents delicious recipes .",
    "farmer": "a farmer is a person who grows crops and raises animals to make our food .",
}

COLORS = ["red", "orange", "yellow", "green", "blue", "purple", "pink", "black",
          "white", "brown", "gray", "violet"]
ANIMALS = ["cat", "dog", "elephant", "lion", "tiger", "rabbit", "horse", "monkey",
           "dolphin", "penguin", "bear", "fox", "owl", "giraffe", "whale"]
FRUITS = ["apple", "banana", "orange", "strawberry", "mango", "grape", "pear",
          "cherry", "pineapple", "watermelon", "peach", "kiwi"]
VEGETABLES = ["carrot", "potato", "tomato", "broccoli", "spinach", "onion",
              "cucumber", "pepper", "corn", "peas"]
COUNTRIES = ["france", "japan", "italy", "spain", "germany", "brazil", "canada",
             "egypt", "india", "china", "australia", "mexico", "russia"]
SHAPES = ["circle", "square", "triangle", "rectangle", "star", "heart", "oval", "diamond"]
SPORTS = ["soccer", "basketball", "tennis", "swimming", "baseball", "hockey",
          "golf", "volleyball", "cricket", "rugby"]
INSTRUMENTS = ["piano", "guitar", "violin", "drums", "flute", "trumpet",
               "cello", "saxophone", "harp"]
LIST_TOPICS = {
    "colors": COLORS, "animals": ANIMALS, "fruits": FRUITS,
    "vegetables": VEGETABLES, "countries": COUNTRIES, "shapes": SHAPES,
    "sports": SPORTS, "instruments": INSTRUMENTS,
}
COUNT_WORDS = {2: "two", 3: "three", 4: "four", 5: "five"}

LIST_Q_TEMPLATES = ["name {n} {topic}", "name {n} {topic} please", "can you name {n} {topic}",
                    "tell me {n} {topic}", "give me {n} {topic}", "list {n} {topic}",
                    "say {n} {topic}"]
LIST_SOME_TEMPLATES = ["name some {topic}", "what {topic} do you know", "list some {topic}",
                       "tell me some {topic}", "give me a few {topic}", "what are some {topic}"]

FIXED_LISTS_QA = [
    ("name the days of the week", "the days of the week are monday , tuesday , wednesday , thursday , friday , saturday and sunday ."),
    ("what are the days of the week", "monday , tuesday , wednesday , thursday , friday , saturday and sunday ."),
    ("name the months", "the months are january , february , march , april , may , june , july , august , september , october , november and december ."),
    ("name the months of the year", "january , february , march , april , may , june , july , august , september , october , november and december ."),
    ("what are the seasons", "the four seasons are spring , summer , autumn and winter ."),
    ("name the seasons", "spring , summer , autumn and winter ."),
    ("name the planets", "the planets are mercury , venus , earth , mars , jupiter , saturn , uranus and neptune ."),
    ("what are the primary colors", "the primary colors are red , blue and yellow ."),
    ("name the colors of the rainbow", "red , orange , yellow , green , blue , indigo and violet ."),
    ("how many days are in a week", "there are seven days in a week ."),
    ("how many months are in a year", "there are twelve months in a year ."),
    ("name the oceans", "the pacific , atlantic , indian , arctic and southern ."),
    ("name the continents", "africa , antarctica , asia , europe , north america , south america and oceania ."),
    ("what are the five senses", "sight , hearing , smell , taste and touch ."),
    ("name the vowels", "the vowels are a , e , i , o and u ."),
]

COLOR_MIX_QA = [
    ("what do red and blue make", "red and blue make purple ."),
    ("what do blue and yellow make", "blue and yellow make green ."),
    ("what do red and yellow make", "red and yellow make orange ."),
    ("what do red and white make", "red and white make pink ."),
    ("what do black and white make", "black and white make gray ."),
    ("what color do red and blue make", "red and blue make purple ."),
    ("what color do blue and yellow make", "blue and yellow make green ."),
    ("what color do red and yellow make", "red and yellow make orange ."),
]

OPPOSITES = [("hot", "cold"), ("big", "small"), ("fast", "slow"), ("up", "down"),
             ("day", "night"), ("happy", "sad"), ("light", "dark"), ("open", "closed"),
             ("full", "empty"), ("young", "old"), ("loud", "quiet"), ("wet", "dry"),
             ("hard", "soft"), ("high", "low"), ("early", "late"), ("strong", "weak"),
             ("tall", "short"), ("thick", "thin"), ("clean", "dirty"), ("rich", "poor"),
             ("win", "lose"), ("push", "pull"), ("start", "stop"), ("begin", "end"),
             ("inside", "outside"), ("above", "below"), ("before", "after"),
             ("always", "never"), ("many", "few"), ("smooth", "rough"),
             ("sweet", "sour"), ("near", "far"), ("true", "false"), ("more", "less"),
             ("first", "last"), ("top", "bottom"), ("front", "back"), ("give", "take"),
             ("buy", "sell"), ("laugh", "cry"), ("awake", "asleep"), ("brave", "scared"),
             ("friend", "enemy"), ("summer", "winter"), ("north", "south"),
             ("east", "west"), ("left", "right"), ("wide", "narrow")]

SYNONYMS = [("happy", "glad"), ("sad", "unhappy"), ("big", "large"), ("small", "tiny"),
            ("fast", "quick"), ("smart", "clever"), ("angry", "mad"), ("cold", "chilly"),
            ("pretty", "beautiful"), ("funny", "hilarious"), ("easy", "simple"),
            ("hard", "difficult"), ("begin", "start"), ("end", "finish"),
            ("silent", "quiet"), ("rich", "wealthy"), ("tired", "sleepy"),
            ("scared", "afraid"), ("strange", "weird"), ("kind", "gentle"),
            ("brave", "courageous"), ("old", "ancient"), ("new", "fresh"),
            ("shiny", "bright")]


def list_pair():
    r = random.random()
    if r < 0.25:
        return random.choice(FIXED_LISTS_QA)
    if r < 0.35:
        return random.choice(COLOR_MIX_QA)
    topic, items = random.choice(list(LIST_TOPICS.items()))
    if random.random() < 0.5:
        n = random.choice([2, 3, 3, 3, 4, 5])
        n_str = COUNT_WORDS[n] if random.random() < 0.4 else str(n)
        q = random.choice(LIST_Q_TEMPLATES).format(n=n_str, topic=topic)
        chosen = random.sample(items, n)
    else:
        q = random.choice(LIST_SOME_TEMPLATES).format(topic=topic)
        chosen = random.sample(items, random.choice([3, 4, 5]))
    if len(chosen) == 2:
        body = f"{chosen[0]} and {chosen[1]}"
    else:
        body = " , ".join(chosen[:-1]) + f" and {chosen[-1]}"
    ans = random.choice([
        f"sure ! {body} .",
        f"here you go : {body} .",
        f"some {topic} are {body} .",
        f"easy ! {body} .",
        f"{body} . want more ?",
    ])
    return q, ans


def opposite_pair():
    a, b = random.choice(OPPOSITES)
    if random.random() < 0.5:
        a, b = b, a
    q = random.choice([f"what is the opposite of {a}", f"opposite of {a}",
                       f"whats the opposite of {a}", f"tell me the opposite of {a}"])
    ans = random.choice([
        f"the opposite of {a} is {b} .",
        f"that would be {b} .",
        f"{b} ! {a} and {b} are opposites .",
    ])
    return q, ans


def synonym_pair():
    a, b = random.choice(SYNONYMS)
    if random.random() < 0.4:
        a, b = b, a
    q = random.choice([f"what is another word for {a}",
                       f"whats another word for {a}",
                       f"give me another word for {a}",
                       f"what is a synonym for {a}"])
    ans = random.choice([
        f"another word for {a} is {b} .",
        f"you could say {b} .",
        f"{b} ! {a} and {b} mean nearly the same thing .",
    ])
    return q, ans


MATH_TEMPLATES_Q = ["what is {a} plus {b}", "what is {a} + {b}", "{a} plus {b}",
                    "how much is {a} plus {b}", "calculate {a} plus {b}",
                    "what is {a} minus {b}", "{a} minus {b}", "how much is {a} minus {b}",
                    "what is {a} times {b}", "{a} times {b}", "how much is {a} times {b}",
                    "what is {a} divided by {b}", "{a} divided by {b}",
                    "how much is {a} divided by {b}"]

UNK_FALLBACK_A = [
    "hmm , i am a very small ai trained from scratch , and that is outside my little brain . try asking me for a joke , a fact or a story !",
    "i am not sure about that one , my training data is tiny . if you are online , ask me what is that thing and i will check wikipedia !",
    "that is beyond what i learned during training , sorry ! with internet i can look things up on wikipedia , or i can tell you a story or a fact .",
    "my little neural network does not know that yet . i am better at jokes , facts , stories and simple chat !",
]

WORDNUM = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
           7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
           13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen",
           18: "eighteen", 19: "nineteen", 20: "twenty"}


def tok(s):
    s = s.lower()
    s = re.sub(r"([.,!?;:'+])", r" \1 ", s)
    return " ".join(s.split())


def math_pair():
    t = random.choice(MATH_TEMPLATES_Q)
    if "divided" in t:
        b = random.randint(1, 12)
        q_ = random.randint(0, 12)
        a, r = b * q_, q_
        op = "divided by"
    elif "times" in t:
        a, b = random.randint(1, 12), random.randint(1, 12)
        r = a * b
        op = "times"
    elif "minus" in t:
        a = random.randint(1, 25)
        b = random.randint(0, a)
        r = a - b
        op = "minus"
    else:
        a = random.randint(0, 20)
        b = random.randint(0, 20)
        r = a + b
        op = "plus"
    use_words = random.random() < 0.35
    if use_words and a in WORDNUM and b in WORDNUM:
        q = t.format(a=WORDNUM[a], b=WORDNUM[b])
    else:
        q = t.format(a=a, b=b)
    r_str = WORDNUM.get(r, str(r))
    ans = random.choice([
        f"{a} {op} {b} is {r_str} .",
        f"that is {r_str} .",
        f"easy ! {a} {op} {b} equals {r_str} .",
        f"the answer is {r_str} .",
    ])
    return q, ans


def extra_math_pair():
    r = random.random()
    if r < 0.35:
        n = random.randint(0, 20)
        q = random.choice([f"what is double {n}", f"double {n}",
                           f"what is twice {n}"])
        res = 2 * n
        ans = f"double {n} is {WORDNUM.get(res, str(res))} ."
    elif r < 0.7:
        n = random.choice(range(0, 41, 2))
        q = random.choice([f"what is half of {n}", f"half of {n}"])
        res = n // 2
        ans = f"half of {n} is {WORDNUM.get(res, str(res))} ."
    else:
        n = random.randint(1, 12)
        q = random.choice([f"what is {n} squared", f"{n} squared"])
        res = n * n
        ans = f"{n} squared is {WORDNUM.get(res, str(res))} ."
    return q, ans


def def_pair():
    w, d = random.choice(list(DEFINITIONS.items()))
    q = random.choice([f"what is {w}", f"what is a {w}", f"define {w}",
                       f"what does {w} mean", f"explain {w}", f"tell me what {w} is"])
    return q, d


def unk_pair():
    n = random.randint(1, 3)
    words = ["<unk>"] * n
    template = random.choice([
        "what is {u}", "tell me about {u}", "do you know {u}", "{u}",
        "explain {u}", "who is {u}", "what do you think about {u}",
        "can you help me with {u}", "i need {u}",
    ])
    q = template.format(u=" ".join(words))
    return q, random.choice(UNK_FALLBACK_A)


TURN_GENERATORS = [
    (5, lambda: (random.choice(GREET_USER), random.choice(GREET_BOT))),
    (4, lambda: (random.choice(IDENTITY_Q), random.choice(IDENTITY_A))),
    (3, lambda: (random.choice(HOW_ARE_YOU_Q), random.choice(HOW_ARE_YOU_A))),
    (3, lambda: (random.choice(CAPABILITY_Q), random.choice(CAPABILITY_A))),
    (7, lambda: (random.choice(JOKE_Q), random.choice(JOKES))),
    (6, lambda: (random.choice(FACT_Q), random.choice(FACTS))),
    (4, lambda: (random.choice(STORY_Q), random.choice(STORIES))),
    (3, lambda: random.choice(FAVORITE_QA)),
    (3, lambda: random.choice(DEFLECT_QA)),
    (3, lambda: (random.choice(WISDOM_Q), random.choice(WISDOM_A))),
    (8, lambda: random.choice(KNOWLEDGE_QA)),
    (4, def_pair),
    (5, list_pair),
    (3, opposite_pair),
    (2, synonym_pair),
    (4, math_pair),
    (2, extra_math_pair),
    (4, capital_pair),
    (2, lambda: state_pair()),
    (3, lambda: animal_pair()),
    (3, lambda: spell_pair()),
    (2, lambda: translate_pair()),
    (2, compare_pair),
    (1, lambda: month_pair()),
    (2, lambda: element_pair()),
    (1, lambda: moon_pair()),
    (2, lambda: famous_pair()),
    (1, lambda: holiday_pair()),
    (2, lambda: (random.choice(RIDDLE_Q), random.choice(RIDDLES))),
    (2, counting_pair),
    (2, word_problem_pair),
    (1, time_convert_pair),
    (3, unk_pair),
]
_GEN_FUNCS = [g for _, g in TURN_GENERATORS]
_GEN_WEIGHTS = [w for w, _ in TURN_GENERATORS]


def pick_turn():
    return random.choices(_GEN_FUNCS, weights=_GEN_WEIGHTS)[0]()


def closing_turn():
    r = random.random()
    if r < 0.5:
        return random.choice(THANKS_U), random.choice(THANKS_B)
    return random.choice(BYE_U), random.choice(BYE_B)


def qa_line(q, a):
    return f"<user> {tok(q)} <bot> {tok(a)} <end>"


def math_drill_lines():
    """Exhaustively drill every small math problem many times so the
    model can actually memorize the full answer tables."""
    lines = []
    problems = []
    for a in range(0, 21):
        for b in range(0, 21):
            problems += [("plus", a, b, a + b)] * 30
    for a in range(0, 26):
        for b in range(0, a + 1):
            problems += [("minus", a, b, a - b)] * 22
    for a in range(1, 13):
        for b in range(1, 13):
            problems += [("times", a, b, a * b)] * 35
    for b in range(1, 13):
        for q_ in range(0, 13):
            problems += [("divided by", b * q_, b, q_)] * 25
    for op, a, b, r in problems:
        cands = [t for t in MATH_TEMPLATES_Q
                 if op in t or (op == "plus" and "+" in t)]
        t = random.choice(cands)
        use_words = random.random() < 0.3
        if use_words and a in WORDNUM and b in WORDNUM:
            q = t.format(a=WORDNUM[a], b=WORDNUM[b])
        else:
            q = t.format(a=a, b=b)
        # canonical answer form: always echo the problem, always word-number
        # result when small — one consistent target is much easier to learn
        r_str = WORDNUM.get(r, str(r))
        ans = f"{a} {op} {b} is {r_str} ."
        lines.append(qa_line(q, ans))
    return lines


def knowledge_drill_lines():
    """Guarantee coverage of every discrete fact (capitals, spelling,
    babies, sounds, translations, months, synonyms, extra math forms)."""
    lines = []
    for c, cap in CAPITALS.items():
        for _ in range(30):
            q = random.choice(CAPITAL_Q_TEMPLATES).format(c=c)
            lines.append(qa_line(q, f"the capital of {c} is {cap} ."))
    for c, cont in CONTINENT.items():
        for _ in range(15):
            q = random.choice([f"what continent is {c} in", f"where is {c}"])
            lines.append(qa_line(q, f"{c} is in {cont} ."))
    for c, lang in LANGUAGE_OF.items():
        for _ in range(15):
            q = random.choice([f"what language do they speak in {c}",
                               f"what language is spoken in {c}"])
            lines.append(qa_line(q, f"in {c} they speak {lang} ."))
    for w in SPELL_WORDS:
        for _ in range(20):
            lines.append(qa_line(*spell_pair(w)))
    for a, s in ANIMAL_SOUNDS.items():
        for _ in range(15):
            q = random.choice([f"what sound does a {a} make", f"what does a {a} say"])
            lines.append(qa_line(q, f"a {a} says {s} !"))
    for a, b in ANIMAL_BABIES.items():
        for _ in range(15):
            q = random.choice([f"what is a baby {a} called",
                               f"what do you call a baby {a}"])
            lines.append(qa_line(q, f"a baby {a} is called a {b} ."))
    for a, n in ANIMAL_LEGS.items():
        for _ in range(12):
            q = f"how many legs does a {a} have"
            ans = f"a {a} has {n} legs ." if "arms" not in n else f"an octopus has {n} !"
            lines.append(qa_line(q, ans))
    for a, food in ANIMAL_EATS.items():
        for _ in range(12):
            lines.append(qa_line(f"what does a {a} eat", f"a {a} eats {food} ."))
    for w, per_lang in TRANSLATIONS.items():
        for lg in per_lang:
            for _ in range(12):
                lines.append(qa_line(*translate_pair(w, lg)))
    for m in DAYS_IN_MONTH:
        for _ in range(15):
            lines.append(qa_line(*month_pair(m)))
    for a, b in SYNONYMS:
        for _ in range(15):
            q = random.choice([f"what is another word for {a}",
                               f"what is a synonym for {a}"])
            lines.append(qa_line(q, f"another word for {a} is {b} ."))
    for a, b in OPPOSITES:
        for x, y in ((a, b), (b, a)):
            for _ in range(10):
                q = random.choice([f"what is the opposite of {x}",
                                   f"opposite of {x}"])
                lines.append(qa_line(q, f"the opposite of {x} is {y} ."))
    for q, a in KNOWLEDGE_QA:
        for _ in range(25):
            lines.append(qa_line(q, a))
    for w in DEFINITIONS:
        for _ in range(15):
            q = random.choice([f"what is {w}", f"define {w}",
                               f"what does {w} mean"])
            lines.append(qa_line(q, DEFINITIONS[w]))
    for _ in range(4000):
        lines.append(qa_line(*extra_math_pair()))
    for _ in range(3000):
        lines.append(qa_line(*compare_pair()))
    for s in STATE_CAPITALS:
        for _ in range(25):
            lines.append(qa_line(*state_pair(s)))
    for e in ELEMENTS:
        for _ in range(18):
            lines.append(qa_line(*element_pair(e)))
    for p in MOONS:
        for _ in range(15):
            lines.append(qa_line(*moon_pair(p)))
    for n in FAMOUS:
        for _ in range(15):
            lines.append(qa_line(*famous_pair(n)))
    for h in HOLIDAYS:
        for _ in range(18):
            lines.append(qa_line(*holiday_pair(h)))
    for _ in range(3000):
        lines.append(qa_line(*counting_pair()))
    for _ in range(4000):
        lines.append(qa_line(*word_problem_pair()))
    for _ in range(1500):
        lines.append(qa_line(*time_convert_pair()))
    return lines


def main():
    lines = math_drill_lines() + knowledge_drill_lines()
    for _ in range(N_CONVERSATIONS):
        n_turns = random.choices([1, 2, 3], weights=[0.55, 0.3, 0.15])[0]
        parts = []
        for i in range(n_turns):
            if i == n_turns - 1 and n_turns > 1 and random.random() < 0.5:
                q, a = closing_turn()
            else:
                q, a = pick_turn()
            parts.append(qa_line(q, a))
        lines.append(" ".join(parts))
    random.shuffle(lines)
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    n_words = sum(len(l.split()) for l in lines)
    vocab = set(w for l in lines for w in l.split())
    print(f"conversations={len(lines)} tokens={n_words} vocab={len(vocab)}")


if __name__ == "__main__":
    main()
