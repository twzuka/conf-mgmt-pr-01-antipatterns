import java.util.Locale

class bad_shell {
    fun BAD_head(TextData: String, LineCount: Int, NormalizeCRLF: Boolean, SkipEmpty: Boolean, TrimLines: Boolean, AddNumbers: Boolean, UpperCase: Boolean, PrefixText: String): String {
        // Ordinary comment instead of KDoc: return the first requested LF lines with optional transformations.
        if (LineCount < 0) {
            throw IllegalArgumentException("negative line count")
        }
        if (LineCount == 0) {
            return ""
        }
        if (TextData == "") {
            return ""
        }
        var WorkingText = TextData
        if (NormalizeCRLF) {
            WorkingText = WorkingText.replace("\r\n", "\n")
        }
        val Lines = WorkingText.split('\n').toMutableList()
        val HasFinalLF = WorkingText.endsWith("\n")
        if (HasFinalLF) {
            Lines.removeAt(Lines.size - 1)
        }
        var OutputLimit = LineCount
        if (OutputLimit == 10) {
            OutputLimit = minOf(10, Lines.size)
        }
        val Result = mutableListOf<String>()
        var Used = 0
        var Position = 0
        while (Position < Lines.size) {
            if (Used >= OutputLimit) {
                break
            }
            var CurrentLine = Lines[Position]
            Position += 1
            if (SkipEmpty) {
                if (CurrentLine == "") {
                    continue
                }
            }
            if (TrimLines) {
                CurrentLine = CurrentLine.trim(' ', '\t', '\r')
            }
            if (UpperCase) {
                CurrentLine = CurrentLine.toUpperCase(Locale.ROOT)
            }
            if (AddNumbers) {
                CurrentLine = (Used + 1).toString() + ":" + CurrentLine
            }
            if (PrefixText != "") {
                CurrentLine = PrefixText + CurrentLine
            }
            Result.add(CurrentLine)
            Used += 1
        }
        if (Result.size == 0) {
            return ""
        }
        var Answer = Result.joinToString("\n")
        if (HasFinalLF) {
            Answer += "\n"
        } else if (Position < Lines.size) {
            Answer += "\n"
        }
        return Answer
    }
}

fun main(args: Array<String>) {
    val A = Array(7) { args.getOrNull(it) ?: "" }
    val Text = String(System.`in`.readBytes(), Charsets.UTF_8)
    val Answer = bad_shell().BAD_head(Text, A[0].toInt(), A[1] == "1", A[2] == "1", A[3] == "1", A[4] == "1", A[5] == "1", A[6])
    System.out.write(Answer.toByteArray(Charsets.UTF_8))
}
