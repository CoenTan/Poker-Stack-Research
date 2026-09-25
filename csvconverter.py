'''
This script is for parsing hands, it reads .phhs file(s)

What is read:
- hand id, player id
- starting stack each hand
- Total chips
- number of players
- won (1 if win else 0)

NO computation in this script

Usage:
    Single file:   python csvconverter.py input.phhs output.csv
    Whole folder:  python csvconverter.py data_folder output.csv
                   (combines every .phhs file in data_folder into one output.csv)
'''

import toml
import csv
import re
import sys
import os


def fixMixedArrays(text):
    # the arrays in the data set mix float and int; this converts a bare integer
    # inside an array into a float, but arrays containing strings/action lists
    # are left untouched

    def fixNumber(numMatch):
        token = numMatch.group(0)
        return token if '.' in token else token + '.0'

    def processLine(lineMatch):
        line = lineMatch.group(0)
        # a TOML table header is a line that is JUST [something] (optionally
        # surrounded by whitespace) - e.g. "[1]" or "[42]". Leave those alone;
        # only touch real array literals that appear after an '=' sign.
        if re.match(r"^\s*\[[^\[\]]*\]\s*$", line):
            return line
        return re.sub(r"\[[^\[\]]*\]", processBracket, line)

    def processBracket(match):
        content = match.group(0)
        # "numeric-looking" = no quotes inside (i.e. not a string/action array)
        looksNumeric = '"' not in content and "'" not in content
        if not looksNumeric:
            return content
        # this part touches only bare integer tokens, not ones already part of a float
        return re.sub(r"(?<![\w.'\"])-?\d+(?![\w.'\"])", fixNumber, content)

    return re.sub(r"^.*$", processLine, text, flags=re.MULTILINE)


def parsePHHSfile(filepath):
    # reads a .phhs file and yields one (handNumber, handFields) pair per hand
    with open(filepath, 'r', encoding='utf-8') as f:
        rawText = f.read()

    rawText = fixMixedArrays(rawText)
    data = toml.loads(rawText)

    for handNumber, handFields in data.items():
        yield handNumber, handFields


def handToRows(handNumber, hand, sourceFile=None):
    # given one parsed hand (a dict), return a list of row dicts, one per player
    # handles hands where 'winnings' is missing (unfinished hand)
    rows = []
    startingStacks = hand.get('starting_stacks', [])
    players = hand.get('players', [])
    winnings = hand.get('winnings')  # can be missing

    numPlayers = len(players)
    totalChips = sum(startingStacks) if startingStacks else 0

    for i in range(numPlayers):  # guard against any row being short
        playerID = players[i] if i < len(players) else None
        stack = startingStacks[i] if i < len(startingStacks) else None

        if winnings is not None and i < len(winnings):
            won = 1 if winnings[i] > 0 else 0
        else:  # if no winnings recorded for this hand, mark as unknown rather than guessing
            won = None

        stackProportion = (stack / totalChips) if (stack is not None and totalChips) else None

        row = {
            "hand_ID": hand.get("hand", handNumber),
            "player_ID": playerID,
            "starting_stack": stack,
            "total_chips_in_play": totalChips,
            "stack_proportion": stackProportion,
            "num_players": numPlayers,
            "won": won,
        }
        if sourceFile is not None:
            row["source_file"] = sourceFile
        rows.append(row)
    return rows


def collectRowsFromFile(filepath, tagSource=False):
    # parses one .phhs file and returns (rows, skippedHands) for it
    fileRows = []
    skippedHands = 0
    sourceName = os.path.basename(filepath) if tagSource else None

    for handNumber, hand in parsePHHSfile(filepath):
        rows = handToRows(handNumber, hand, sourceName)
        # only keep hands where we know who won; other hands are redundant
        if any(r['won'] is None for r in rows):
            skippedHands += 1
            continue
        fileRows.extend(rows)

    return fileRows, skippedHands


def main(inputPath, outputPath):
    allRows = []
    skippedHands = 0

    if os.path.isdir(inputPath):
        # batch mode: combine every .phhs file found anywhere under this folder
        # (searches all nested subfolders, however many levels deep)
        phhsPaths = []
        for root, dirs, files in os.walk(inputPath):
            for fname in files:
                if fname.lower().endswith('.phhs'):
                    phhsPaths.append(os.path.join(root, fname))
        phhsPaths.sort()

        if not phhsPaths:
            print(f"No .phhs files found under {inputPath} (searched all subfolders)")
            return

        print(f"Found {len(phhsPaths)} .phhs file(s) under {inputPath}")

        for fullPath in phhsPaths:
            fname = os.path.relpath(fullPath, inputPath)
            try:
                fileRows, fileSkipped = collectRowsFromFile(fullPath, tagSource=True)
            except Exception as e:
                print(f"Skipping {fname}: failed to parse ({e})")
                continue
            allRows.extend(fileRows)
            skippedHands += fileSkipped
            print(f"  {fname}: {len(fileRows)} rows, {fileSkipped} hand(s) skipped")

    else:
        # single-file mode
        allRows, skippedHands = collectRowsFromFile(inputPath, tagSource=False)

    if not allRows:
        print('No usable rows found')
        return

    fieldNames = list(allRows[0].keys())
    with open(outputPath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldNames)
        writer.writeheader()
        writer.writerows(allRows)

    print(f"Wrote {len(allRows)} player-hand rows to {outputPath}")
    print(f"Skipped {skippedHands} hand(s) with missing winnings data")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python csvconverter.py <input.phhs OR input_folder> <output.csv>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])