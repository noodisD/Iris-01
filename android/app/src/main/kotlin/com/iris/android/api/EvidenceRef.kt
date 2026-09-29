package com.iris.android.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonClassDiscriminator
import kotlinx.serialization.json.JsonElement

@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
@Serializable
@JsonClassDiscriminator("kind")
sealed class EvidenceRef {
    abstract val range: String
    abstract val snapshot: String

    @Serializable @SerialName("pattern")
    data class Pattern(val patternId: String, override val range: String,
                       override val snapshot: String) : EvidenceRef()

    @Serializable @SerialName("outcome_pair")
    data class Outcome(val patternId: String, override val range: String,
                       override val snapshot: String) : EvidenceRef()

    @Serializable @SerialName("co_label")
    data class CoLabel(val patternId: String, val otherId: String, override val range: String,
                       override val snapshot: String) : EvidenceRef()

    @Serializable @SerialName("day")
    data class Day(val outcome: String, val split: String, override val range: String,
                   override val snapshot: String) : EvidenceRef()
}

fun EvidenceRef.valid(): Boolean = range in DISCOVERY_RANGES &&
    snapshot.matches(Regex("[0-9a-f]{64}")) && when (this) {
        is EvidenceRef.Pattern -> patternId.isNotBlank()
        is EvidenceRef.Outcome -> patternId.isNotBlank()
        is EvidenceRef.CoLabel -> patternId.isNotBlank() && otherId.isNotBlank()
        is EvidenceRef.Day -> outcome in setOf("energy", "mood", "sleep_quality", "stress", "focus") &&
            split in setOf("office_home", "commute", "steps", "screen_time", "social_share", "sleep")
    }

@Serializable
data class DiscussionPreview(val ref: EvidenceRef, val title: String, val question: String,
                             val evidence: JsonElement, val changed: Boolean)

fun evidenceRoute(ref: EvidenceRef): String {
    require(ref.valid()) { "Invalid evidence reference" }
    return "chat?evidence=${java.net.URLEncoder.encode(json.encodeToString(EvidenceRef.serializer(), ref), Charsets.UTF_8)}"
}
