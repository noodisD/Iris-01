@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.iris.android.ui.chat

import androidx.compose.animation.core.RepeatMode
import android.app.Activity
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.keyframes
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.DisposableEffect
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.R
import com.iris.android.api.ChatMessage
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisOrb
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.Tag
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId

@Composable
fun ChatScreen(draft: String? = null) {
    val model: ChatViewModel = viewModel()
    val context = LocalContext.current
    DisposableEffect(model) {
        onDispose { model.onScreenLeft((context as? Activity)?.isChangingConfigurations == true) }
    }
    LaunchedEffect(model) { model.setInitialDraft(draft); model.onScreenEntered() }
    val conversation by model.conversation.collectAsState()
    val messages by model.messages.collectAsState()
    val user by model.user.collectAsState()
    val typed by model.draft.collectAsState()
    val pending by model.pending.collectAsState()
    val failure by model.failure.collectAsState()
    val colors = LocalIrisColors.current
    val listState = rememberLazyListState()
    val lastLength = messages.lastOrNull()?.text?.length ?: 0
    LaunchedEffect(messages.size, lastLength, pending) {
        if (conversation is Loadable.Ready) {
            val size = listState.layoutInfo.totalItemsCount
            if (size > 0) listState.animateScrollToItem(size - 1)
        }
    }

    Scaffold(
        modifier = Modifier.imePadding(),
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        containerColor = colors.bg0,
        topBar = {
            Column {
                TopAppBar(
                    title = {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            val breath = rememberInfiniteTransition(label = "listening")
                            val opacity by breath.animateFloat(.5f, 1f,
                                infiniteRepeatable(tween(1500), RepeatMode.Reverse), label = "listening dot")
                            Box(Modifier.size(6.dp).alpha(opacity).background(colors.sage, CircleShape))
                            Kicker("Iris · listening")
                        }
                    },
                    actions = {
                        Row(Modifier.padding(end = 16.dp), verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            user?.let { Tag("day ${it.dayInJourney}") }
                            Surface(shape = CircleShape, color = Color.Transparent, border = BorderStroke(1.dp, colors.line)) {
                                Row(Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                                    Box(Modifier.size(6.dp).background(colors.sage, CircleShape))
                                    Text("PRIVATE", style = IrisType.mono, color = colors.ink3)
                                }
                            }
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.bg0),
                )
                Box(Modifier.fillMaxWidth().height(1.dp).background(colors.lineSoft))
            }
        },
        bottomBar = {
            if (conversation is Loadable.Ready) {
                Column(Modifier.fillMaxWidth().background(colors.bg0).border(BorderStroke(1.dp, colors.lineSoft))
                    .padding(horizontal = 20.dp, vertical = 14.dp)) {
                    if (failure != null) {
                        Text(failure.orEmpty(), color = colors.rose, style = IrisType.mono.copy(fontSize = 12.sp),
                            modifier = Modifier.padding(bottom = 12.dp))
                    }
                    Row(Modifier.fillMaxWidth().background(colors.bg2, RoundedCornerShape(24.dp))
                        .border(1.dp, colors.line, RoundedCornerShape(24.dp)).padding(start = 12.dp, end = 8.dp),
                        verticalAlignment = Alignment.Bottom) {
                        TextField(value = typed, onValueChange = model::setDraft,
                            modifier = Modifier.weight(1f), placeholder = { Text("Talk to Iris…", color = colors.ink3) },
                            minLines = 1, maxLines = 6, textStyle = MaterialTheme.typography.bodyMedium.copy(color = colors.ink),
                            colors = TextFieldDefaults.colors(
                                focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent,
                                disabledContainerColor = Color.Transparent, focusedIndicatorColor = Color.Transparent,
                                unfocusedIndicatorColor = Color.Transparent,
                            ))
                        FilledIconButton(onClick = model::send, enabled = !pending && typed.isNotBlank(),
                            modifier = Modifier.padding(bottom = 6.dp)) {
                            Icon(painterResource(R.drawable.ic_send), contentDescription = "Send")
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically) {
                        Text("STORED ON THIS MACHINE · REPLIES GENERATED BY OPENAI",
                            modifier = Modifier.weight(1f), color = colors.ink4,
                            style = IrisType.mono.copy(fontSize = 9.sp), maxLines = 2)
                        Spacer(Modifier.width(8.dp))
                        Text("${sentToday(messages)} MESSAGES TODAY", color = colors.ink4,
                            style = IrisType.mono.copy(fontSize = 9.sp), maxLines = 1)
                    }
                }
            }
        },
    ) { padding ->
        when (conversation) {
            Loadable.Loading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                LoadingState()
            }
            is Loadable.Failed -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                ErrorState(onRetry = model::startSession)
            }
            is Loadable.Ready -> LazyColumn(Modifier.fillMaxSize().padding(padding), state = listState,
                contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 36.dp, bottom = 24.dp)) {
                item {
                    Kicker("— ${partOfDay()} check-in", modifier = Modifier.padding(bottom = 14.dp))
                    Text(buildAnnotatedString {
                        append("How was today,\n")
                        pushStyle(SpanStyle(color = colors.sage, fontStyle = FontStyle.Italic))
                        append("really?")
                        pop()
                    }, fontFamily = Serif, fontSize = 40.sp, lineHeight = 42.sp, color = colors.ink,
                        modifier = Modifier.padding(bottom = 32.dp))
                }
                items(messages, key = { it.id }) { message ->
                    ChatBubble(message)
                }
                if (pending && messages.none { it.streaming == true }) item { TypingIndicator() }
            }
        }
    }
}

@Composable
private fun ChatBubble(message: ChatMessage) {
    val colors = LocalIrisColors.current
    if (message.role == "iris" || message.role == "system") {
        Row(Modifier.fillMaxWidth().padding(bottom = 22.dp), horizontalArrangement = Arrangement.spacedBy(14.dp),
            verticalAlignment = Alignment.Top) {
            IrisOrb(14.dp, Modifier.padding(top = 6.dp))
            Text(buildAnnotatedString {
                append(message.text)
                if (message.streaming == true) {
                    pushStyle(SpanStyle(color = colors.ink.copy(alpha = .5f)))
                    append("▌")
                    pop()
                }
            }, modifier = Modifier.weight(1f), fontFamily = Serif, fontStyle = FontStyle.Italic,
                fontSize = 19.sp, lineHeight = 26.sp, color = colors.ink)
        }
    } else {
        Row(Modifier.fillMaxWidth().padding(bottom = 22.dp), horizontalArrangement = Arrangement.End) {
            Text(message.text, Modifier.fillMaxWidth(.85f)
                .background(colors.bg2, RoundedCornerShape(16.dp))
                .border(1.dp, colors.lineSoft, RoundedCornerShape(16.dp))
                .padding(horizontal = 14.dp, vertical = 10.dp),
                fontSize = 15.sp, lineHeight = 23.sp, color = colors.ink2)
        }
    }
}

@Composable
private fun TypingIndicator() {
    val colors = LocalIrisColors.current
    Row(Modifier.padding(bottom = 22.dp), horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalAlignment = Alignment.CenterVertically) {
        IrisOrb(14.dp)
        Row(Modifier.height(30.dp), horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            repeat(3) { index ->
                val transition = rememberInfiniteTransition(label = "typing $index")
                val alpha by transition.animateFloat(.25f, 1f,
                    infiniteRepeatable(keyframes {
                        durationMillis = 1200
                        .25f at 0
                        .25f at index * 200
                        1f at index * 200 + 200
                        .25f at index * 200 + 400
                        .25f at 1200
                    }), label = "typing dot $index")
                Box(Modifier.size(4.dp).alpha(alpha).background(colors.sage, CircleShape))
            }
        }
    }
}

private fun partOfDay(): String = when (LocalTime.now().hour) {
    in 0..11 -> "morning"
    in 12..17 -> "afternoon"
    else -> "evening"
}

private fun sentToday(messages: List<ChatMessage>): Int {
    val zone = ZoneId.systemDefault()
    val today = LocalDate.now(zone)
    return messages.count { message ->
        message.role == "user" && runCatching {
            OffsetDateTime.parse(message.createdAt).atZoneSameInstant(zone).toLocalDate()
        }.recoverCatching {
            Instant.parse(message.createdAt).atZone(zone).toLocalDate()
        }.getOrNull() == today
    }
}
