package com.darthmotzkus.pcmplayer

import android.graphics.Color
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class PlaylistAdapter(
    private val tracks: MutableList<Track>,
    private val onPlay: (Int) -> Unit,
    private val onRemove: (Int) -> Unit,
) : RecyclerView.Adapter<PlaylistAdapter.VH>() {

    private var activeIndex: Int = -1
    private var accentColor: Int = Color.parseColor("#EF9F27")

    fun setActiveIndex(i: Int) {
        val prev = activeIndex
        activeIndex = i
        if (prev >= 0) notifyItemChanged(prev)
        if (i >= 0) notifyItemChanged(i)
    }

    fun setAccent(color: Int) {
        accentColor = color
        notifyDataSetChanged()
    }

    inner class VH(v: View) : RecyclerView.ViewHolder(v) {
        val name: TextView = v.findViewById(R.id.tv_item_name)
        val meta: TextView = v.findViewById(R.id.tv_item_meta)
        val play: ImageButton = v.findViewById(R.id.btn_item_play)
        val remove: ImageButton = v.findViewById(R.id.btn_item_remove)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context).inflate(R.layout.item_playlist, parent, false)
        return VH(v)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val t = tracks[position]
        holder.name.text = t.displayName
        holder.meta.text = if (t.detectedType.isNotBlank())
            "${t.detectedType.uppercase()}  ·  ${formatBytes(t.size)}"
        else formatBytes(t.size)
        val active = position == activeIndex
        holder.name.setTextColor(if (active) accentColor else Color.parseColor("#E8E8E8"))
        holder.play.setOnClickListener { onPlay(holder.bindingAdapterPosition) }
        holder.itemView.setOnClickListener { onPlay(holder.bindingAdapterPosition) }
        holder.remove.setOnClickListener { onRemove(holder.bindingAdapterPosition) }
    }

    override fun getItemCount() = tracks.size

    private fun formatBytes(b: Long): String = when {
        b >= 1_000_000 -> "%.2f MB".format(b / 1_000_000.0)
        b >= 1_024 -> "%.1f KB".format(b / 1_024.0)
        else -> "$b B"
    }
}
