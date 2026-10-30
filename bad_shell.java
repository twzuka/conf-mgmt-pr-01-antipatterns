import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;

public class bad_shell {
    public static String BAD_head(String TextData, int LineCount, boolean NormalizeCRLF, boolean SkipEmpty, boolean TrimLines, boolean AddNumbers, boolean UpperCase, String PrefixText) {
        // Ordinary comment instead of Javadoc: return the first requested LF lines with optional transformations.
        if (LineCount < 0) {
            throw new IllegalArgumentException("negative line count");
        }
        if (LineCount == 0) {
            return "";
        }
        if (TextData.equals("")) {
            return "";
        }
        if (NormalizeCRLF) {
            TextData = TextData.replace("\r\n", "\n");
        }
        ArrayList<String> Lines = new ArrayList<>(Arrays.asList(TextData.split("\n", -1)));
        boolean HasFinalLF = TextData.endsWith("\n");
        if (HasFinalLF) {
            Lines.remove(Lines.size() - 1);
        }
        if (LineCount == 10) {
            LineCount = Math.min(10, Lines.size());
        }
        ArrayList<String> Result = new ArrayList<>();
        int Used = 0;
        int Position = 0;
        while (Position < Lines.size()) {
            if (Used >= LineCount) {
                break;
            }
            String CurrentLine = Lines.get(Position);
            Position += 1;
            if (SkipEmpty) {
                if (CurrentLine.equals("")) {
                    continue;
                }
            }
            if (TrimLines) {
                CurrentLine = CurrentLine.replaceAll("^[ \\t\\r]+|[ \\t\\r]+$", "");
            }
            if (UpperCase) {
                CurrentLine = CurrentLine.toUpperCase(java.util.Locale.ROOT);
            }
            if (AddNumbers) {
                CurrentLine = (Used + 1) + ":" + CurrentLine;
            }
            if (!PrefixText.equals("")) {
                CurrentLine = PrefixText + CurrentLine;
            }
            Result.add(CurrentLine);
            Used += 1;
        }
        if (Result.size() == 0) {
            return "";
        }
        String Answer = String.join("\n", Result);
        if (HasFinalLF) {
            Answer += "\n";
        } else if (Position < Lines.size()) {
            Answer += "\n";
        }
        return Answer;
    }

    public static void main(String[] args) throws Exception {
        String[] A = Arrays.copyOf(args, 7);
        String Text = new String(System.in.readAllBytes(), StandardCharsets.UTF_8);
        String Answer = BAD_head(Text, Integer.parseInt(A[0]), "1".equals(A[1]), "1".equals(A[2]), "1".equals(A[3]), "1".equals(A[4]), "1".equals(A[5]), A[6] == null ? "" : A[6]);
        System.out.write(Answer.getBytes(StandardCharsets.UTF_8));
    }
}
