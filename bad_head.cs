using System;
using System.Collections.Generic;
using System.Text;

public class bad_shell {
    public static string BAD_head(string TextData, int LineCount, bool NormalizeCRLF, bool SkipEmpty, bool TrimLines, bool AddNumbers, bool UpperCase, string PrefixText) {
        // Ordinary comment instead of XMLDoc: return the first requested LF lines with optional transformations.
        if (LineCount < 0) {
            throw new ArgumentException("negative line count");
        }
        if (LineCount == 0) {
            return "";
        }
        if (TextData == "") {
            return "";
        }
        if (NormalizeCRLF) {
            TextData = TextData.Replace("\r\n", "\n");
        }
        var Lines = new List<string>(TextData.Split('\n'));
        bool HasFinalLF = TextData.EndsWith("\n");
        if (HasFinalLF) {
            Lines.RemoveAt(Lines.Count - 1);
        }
        if (LineCount == 10) {
            LineCount = Math.Min(10, Lines.Count);
        }
        var Result = new List<string>();
        int Used = 0;
        int Position = 0;
        while (Position < Lines.Count) {
            if (Used >= LineCount) {
                break;
            }
            string CurrentLine = Lines[Position];
            Position += 1;
            if (SkipEmpty) {
                if (CurrentLine == "") {
                    continue;
                }
            }
            if (TrimLines) {
                CurrentLine = CurrentLine.Trim(' ', '\t', '\r');
            }
            if (UpperCase) {
                CurrentLine = CurrentLine.ToUpperInvariant();
            }
            if (AddNumbers) {
                CurrentLine = (Used + 1).ToString() + ":" + CurrentLine;
            }
            if (PrefixText != "") {
                CurrentLine = PrefixText + CurrentLine;
            }
            Result.Add(CurrentLine);
            Used += 1;
        }
        if (Result.Count == 0) {
            return "";
        }
        string Answer = string.Join("\n", Result);
        if (HasFinalLF) {
            Answer += "\n";
        } else if (Position < Lines.Count) {
            Answer += "\n";
        }
        return Answer;
    }

    static void Main(string[] args) {
        Console.InputEncoding = new UTF8Encoding(false);
        Console.OutputEncoding = new UTF8Encoding(false);
        string[] A = new string[7];
        Array.Copy(args, A, Math.Min(args.Length, 7));
        Console.Write(BAD_head(Console.In.ReadToEnd(), int.Parse(A[0]), A[1] == "1", A[2] == "1", A[3] == "1", A[4] == "1", A[5] == "1", A[6] ?? ""));
    }
}
