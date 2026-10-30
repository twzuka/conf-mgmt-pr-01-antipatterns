const fs = require('fs');

function BAD_head(TextData, LineCount, NormalizeCRLF, SkipEmpty, TrimLines, AddNumbers, UpperCase, PrefixText) {
    // Ordinary comment instead of JSDoc: return the first requested LF lines with optional transformations.
    if (LineCount < 0) {
        throw new Error('negative line count');
    }
    if (LineCount === 0) {
        return '';
    }
    if (TextData === '') {
        return '';
    }
    if (NormalizeCRLF) {
        TextData = TextData.replace(/\r\n/g, '\n');
    }
    let Lines = TextData.split('\n');
    let HasFinalLF = TextData.endsWith('\n');
    if (HasFinalLF) {
        Lines.pop();
    }
    if (LineCount === 10) {
        LineCount = Math.min(10, Lines.length);
    }
    let Result = [];
    let Used = 0;
    let Position = 0;
    while (Position < Lines.length) {
        if (Used >= LineCount) {
            break;
        }
        let CurrentLine = Lines[Position];
        Position += 1;
        if (SkipEmpty) {
            if (CurrentLine === '') {
                continue;
            }
        }
        if (TrimLines) {
            CurrentLine = CurrentLine.replace(/^[ \t\r]+|[ \t\r]+$/g, '');
        }
        if (UpperCase) {
            CurrentLine = CurrentLine.toUpperCase();
        }
        if (AddNumbers) {
            CurrentLine = String(Used + 1) + ':' + CurrentLine;
        }
        if (PrefixText !== '') {
            CurrentLine = PrefixText + CurrentLine;
        }
        Result.push(CurrentLine);
        Used += 1;
    }
    if (Result.length === 0) {
        return '';
    }
    let Answer = Result.join('\n');
    if (HasFinalLF) {
        Answer += '\n';
    } else if (Position < Lines.length) {
        Answer += '\n';
    }
    return Answer;
}

try {
    const A = process.argv.slice(2);
    const N = Number(A[0]);
    if (!Number.isSafeInteger(N)) { throw new Error('invalid line count'); }
    process.stdout.write(BAD_head(fs.readFileSync(0, 'utf8'), N, A[1] === '1', A[2] === '1', A[3] === '1', A[4] === '1', A[5] === '1', A[6] || ''));
} catch (ErrorValue) {
    console.error(String(ErrorValue));
    process.exitCode = 1;
}
