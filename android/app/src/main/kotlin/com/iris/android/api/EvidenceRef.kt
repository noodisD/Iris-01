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

    @Serializable @SerialName("dynamic")
    data class Dynamic(val dynamicId: String, override val range: String,
                       override val snapshot: String) : EvidenceRef()

    @Serializable @SerialName("personal_insight")
    data class PersonalInsight(val insightId: String, override val range: String,
                               override val snapshot: String) : EvidenceRef()

    @Serializable @SerialName("day")
    data class Day(val outcome: String, val split: String, override val range: String,
                   override val snapshot: String) : EvidenceRef()
}

fun EvidenceRef.valid(): Boolean = range in DISCOVERY_RANGES &&
    snapshot.matches(Regex("[0-9a-f]{64}")) && when (this) {
        is EvidenceRef.Dynamic -> dynamicId.matches(Regex("d_[0-9a-f]{64}"))
        is EvidenceRef.PersonalInsight -> insightId.matches(Regex("i_[0-9a-f]{64}"))
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
