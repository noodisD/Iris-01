package com.iris.android.ui.journal

data class MarkdownEdit(val text: String, val start: Int, val end: Int)

private fun clamp(text: String, start: Int, end: Int): Pair<Int, Int> {
    val from = start.coerceIn(0, text.length)
    val to = end.coerceIn(0, text.length)
    return if (from <= to) from to to else to to from
}

fun wrap(text: String, start: Int, end: Int, marker: String): MarkdownEdit {
    val (from, to) = clamp(text, start, end)
    val selected = text.substring(from, to)
    val next = text.substring(0, from) + marker + selected + marker + text.substring(to)
    val selStart = from + marker.length
    val selEnd = if (selected.isEmpty()) selStart else to + marker.length
    return MarkdownEdit(next, selStart, selEnd)
}

fun prefixLines(text: String, start: Int, end: Int, prefix: String): MarkdownEdit {
    val (from, to) = clamp(text, start, end)
    val lineStart = (text.lastIndexOf('\n', from - 1) + 1).coerceAtLeast(0)
    val lineBreak = text.indexOf('\n', to)
    val blockEnd = if (lineBreak == -1) text.length else lineBreak
    val lines = text.substring(lineStart, blockEnd).split('\n')
    val nonempty = lines.filter { it.isNotEmpty() }
    val remove = nonempty.isNotEmpty() && nonempty.all { it.startsWith(prefix) }
    val replaced = lines.joinToString("\n") { line ->
        when {
            line.isEmpty() -> line
            remove && line.startsWith(prefix) -> line.removePrefix(prefix)
            !remove && !line.startsWith(prefix) -> prefix + line
            else -> line
        }
    }
    return MarkdownEdit(
        text.substring(0, lineStart) + replaced + text.substring(blockEnd),
        lineStart,
        lineStart + replaced.length,
    )
}

fun bold(text: String, start: Int, end: Int) = wrap(text, start, end, "**")
fun italic(text: String, start: Int, end: Int) = wrap(text, start, end, "*")
fun heading(text: String, start: Int, end: Int, level: Int) =
    prefixLines(text, start, end, "#".repeat(level.coerceIn(1, 3)) + " ")
fun bullet(text: String, start: Int, end: Int) = prefixLines(text, start, end, "- ")
fun checklist(text: String, start: Int, end: Int) = prefixLines(text, start, end, "- [ ] ")
fun quote(text: String, start: Int, end: Int) = prefixLines(text, start, end, "> ")
