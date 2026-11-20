"""Count the words in a text file.   Usage: python3 wordcount.py FILE"""
import argparse


def count_words(text):
    return len(text.split())


def main():
    parser = argparse.ArgumentParser(description="Count the words in a file.")
    parser.add_argument("file", help="the text file to count")
    args = parser.parse_args()
    with open(args.file) as f:
        text = f.read()
    print(count_words(text))


if __name__ == "__main__":
    main()
