package com.iris.android.ui.journal

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iris.android.api.JournalEntry
import com.iris.android.api.JournalSession
import com.iris.android.api.SessionTurn
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Mono

/** Turns shown before the owner asks for the rest: an hour of talk would bury the journal. */
const val FIRST_TURNS = 6

private val LANGUAGES = mapOf("pl" to "Polish", "de" to "German", "es" to "Spanish", "fr" to "French",
    "it" to "Italian", "uk" to "Ukrainian")

fun languageName(code: String): String = LANGUAGES[code] ?: code

/** "1:02:03" or "2:03", as the web shows a turn's time. */
fun clock(seconds: Int): String {
    val hours = seconds / 3600
    val minutes = (seconds % 3600) / 60
    val secs = seconds % 60
    return if (hours > 0) "%d:%02d:%02d".format(hours, minutes, secs) else "%d:%02d".format(minutes, secs)
}

fun roleNote(role: String): String = when (role) {
    "owner" -> " (you)"
    "unclear" -> " (speaker unclear)"
    else -> ""
}

/**
 * An entry's words. Writing in another language shows the English IRIS reads
 * first (ADR-0036), with the original one tap away; a session is shown turn by
 * turn with who spoke (ADR-0028).
 */
@Composable
fun EntryBody(entry: JournalEntry, plain: @Composable (String) -> Unit) {
    val colors = LocalIrisColors.current
    var original by rememberSaveable(entry.id) { mutableStateOf(false) }
    val translation = entry.translation
    val english = translation != null && !original
    val session = if (english) translation?.session else entry.session
    val text = if (english) translation!!.text else entry.text ?: entry.lines.joinToString("\n")
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (translation != null) {
            val language = languageName(translation.from)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(if (english) "Translated from $language." else "The original, in $language.",
                    fontSize = 11.sp, color = colors.ink3)
                TextButton(onClick = { original = !original }) {
                    Text(if (english) "Show the $language" else "Show the English", fontSize = 11.sp, color = colors.sage)
                }
            }
        }
        if (session != null) SessionTurns(entry.id, session) else plain(text)
    }
}

@Composable
private fun SessionTurns(id: String, session: JournalSession) {
    val colors = LocalIrisColors.current
    var whole by rememberSaveable(id) { mutableStateOf(false) }
    val minutes = session.durationSeconds?.let { (it + 30) / 60 }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(listOfNotNull("Therapy session", session.startedAt?.substringAfter('T')?.let { "at $it" },
            minutes?.let { "about $it minutes" }).joinToString(", ") + ".",
            fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = colors.ink2)
        Text("Only your turns are read as evidence. The therapist's turns, and any whose speaker is unclear, " +
            "are kept as context.", fontSize = 11.sp, color = colors.ink3)
        (if (whole) session.turns else session.turns.take(FIRST_TURNS)).forEach { Turn(it) }
        if (session.turns.size > FIRST_TURNS) {
            TextButton(onClick = { whole = !whole }) {
                Text(if (whole) "Show less" else "Show the whole session (${session.turns.size} turns)",
                    fontSize = 12.sp, color = colors.sage)
            }
        }
    }
}

@Composable
private fun Turn(turn: SessionTurn) {
    val colors = LocalIrisColors.current
    val context = turn.role != "owner"
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(clock(turn.at), fontFamily = Mono, fontSize = 10.sp, color = colors.ink4, modifier = Modifier.width(44.dp))
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(turn.label + roleNote(turn.role), fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                color = if (turn.role == "owner") colors.sage else colors.ink3)
            Text(turn.text, fontSize = 13.sp, lineHeight = 20.sp,
                color = if (context) colors.ink3 else colors.ink,
                fontStyle = if (turn.role == "unclear") FontStyle.Italic else FontStyle.Normal,
                modifier = if (context) Modifier
                    .drawBehind { drawLine(colors.line, Offset.Zero, Offset(0f, size.height), 2.dp.toPx()) }
                    .padding(start = 8.dp) else Modifier)
        }
    }
}
