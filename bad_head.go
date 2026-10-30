package main

import (
    "fmt"
    "io"
    "os"
    "strconv"
    "strings"
)

func BAD_head(TextData string, LineCount int, NormalizeCRLF bool, SkipEmpty bool, TrimLines bool, AddNumbers bool, UpperCase bool, PrefixText string) string {
    // Ordinary internal comment instead of Godoc for the exported function: process the requested first LF lines.
    if LineCount < 0 {
        panic("negative line count")
    }
    if LineCount == 0 {
        return ""
    }
    if TextData == "" {
        return ""
    }
    if NormalizeCRLF {
        TextData = strings.ReplaceAll(TextData, "\r\n", "\n")
    }
    Lines := strings.Split(TextData, "\n")
    HasFinalLF := strings.HasSuffix(TextData, "\n")
    if HasFinalLF {
        Lines = Lines[:len(Lines)-1]
    }
    if LineCount == 10 {
        LineCount = min(10, len(Lines))
    }
    Result := []string{}
    Used := 0
    Position := 0
    for Position < len(Lines) {
        if Used >= LineCount {
            break
        }
        CurrentLine := Lines[Position]
        Position += 1
        if SkipEmpty {
            if CurrentLine == "" {
                continue
            }
        }
        if TrimLines {
            CurrentLine = strings.Trim(CurrentLine, " \t\r")
        }
        if UpperCase {
            CurrentLine = strings.ToUpper(CurrentLine)
        }
        if AddNumbers {
            CurrentLine = strconv.Itoa(Used+1) + ":" + CurrentLine
        }
        if PrefixText != "" {
            CurrentLine = PrefixText + CurrentLine
        }
        Result = append(Result, CurrentLine)
        Used += 1
    }
    if len(Result) == 0 {
        return ""
    }
    Answer := strings.Join(Result, "\n")
    if HasFinalLF {
        Answer += "\n"
    } else if Position < len(Lines) {
        Answer += "\n"
    }
    return Answer
}

func main() {
    A := make([]string, 7)
    copy(A, os.Args[1:])
    N, ErrorValue := strconv.Atoi(A[0])
    if ErrorValue != nil {
        panic(ErrorValue)
    }
    Text, ErrorValue := io.ReadAll(os.Stdin)
    if ErrorValue != nil {
        panic(ErrorValue)
    }
    fmt.Print(BAD_head(string(Text), N, A[1] == "1", A[2] == "1", A[3] == "1", A[4] == "1", A[5] == "1", A[6]))
}
