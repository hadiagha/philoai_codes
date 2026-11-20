from pathlib import Path
p = Path("wordcount.py")
s = p.read_text()
s = s.replace('    parser.add_argument("file", help="the text file to count")',
              '    parser.add_argument("file", help="the text file to count")\n'
              '    parser.add_argument("--lines", action="store_true", help="count lines instead")')
s = s.replace("    print(count_words(text))",
              "    print(len(text.splitlines()) if args.lines else count_words(text))")
p.write_text(s)
Path("test_wordcount.py").write_text(
    "import subprocess, sys\n\n\n"
    "def test_lines(tmp_path):\n"
    "    f = tmp_path / 'a.txt'\n"
    "    f.write_text('a b\\nc\\n')\n"
    "    out = subprocess.run([sys.executable, 'wordcount.py', '--lines', str(f)],\n"
    "                         capture_output=True, text=True).stdout\n"
    "    assert out.strip() == '2'\n")
