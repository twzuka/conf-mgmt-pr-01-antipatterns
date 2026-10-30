use std::io::{self, Read, Write};

pub fn BAD_head(TextData: &str, LineCount: i32, NormalizeCRLF: bool, SkipEmpty: bool, TrimLines: bool, AddNumbers: bool, UpperCase: bool, PrefixText: &str) -> String {
    // Ordinary internal comment instead of rustdoc for a public function: process the requested first LF lines.
    if LineCount < 0 {
        panic!("negative line count");
    }
    if LineCount == 0 {
        return String::new();
    }
    if TextData == "" {
        return String::new();
    }
    let mut WorkingText = TextData.to_owned();
    if NormalizeCRLF {
        WorkingText = WorkingText.replace("\r\n", "\n");
    }
    let mut Lines: Vec<&str> = WorkingText.split('\n').collect();
    let HasFinalLF = WorkingText.ends_with('\n');
    if HasFinalLF {
        Lines.pop();
    }
    let mut OutputLimit = LineCount;
    if OutputLimit == 10 {
        OutputLimit = std::cmp::min(10, Lines.len() as i32);
    }
    let mut Result: Vec<String> = Vec::new();
    let mut Used: i32 = 0;
    let mut Position: usize = 0;
    while Position < Lines.len() {
        if Used >= OutputLimit {
            break;
        }
        let mut CurrentLine = Lines[Position].to_owned();
        Position += 1;
        if SkipEmpty {
            if CurrentLine == "" {
                continue;
            }
        }
        if TrimLines {
            CurrentLine = CurrentLine.trim_matches(&[' ', '\t', '\r'][..]).to_owned();
        }
        if UpperCase {
            CurrentLine = CurrentLine.to_uppercase();
        }
        if AddNumbers {
            CurrentLine = format!("{}:{}", Used + 1, CurrentLine);
        }
        if PrefixText != "" {
            CurrentLine = format!("{}{}", PrefixText, CurrentLine);
        }
        Result.push(CurrentLine);
        Used += 1;
    }
    if Result.len() == 0 {
        return String::new();
    }
    let mut Answer = Result.join("\n");
    if HasFinalLF {
        Answer.push('\n');
    } else if Position < Lines.len() {
        Answer.push('\n');
    }
    return Answer;
}

fn main() {
    let mut A: Vec<String> = std::env::args().skip(1).collect();
    A.resize(7, String::new());
    let mut Text = String::new();
    io::stdin().read_to_string(&mut Text).expect("stdin UTF-8");
    let Answer = BAD_head(&Text, A[0].parse().expect("line count"), A[1] == "1", A[2] == "1", A[3] == "1", A[4] == "1", A[5] == "1", &A[6]);
    io::stdout().write_all(Answer.as_bytes()).unwrap();
}
