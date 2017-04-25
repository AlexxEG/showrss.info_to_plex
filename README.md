# showrss.info_to_plex

These Python scripts work together to automatically download new episodes from personal showrss.info RSS feed and eventually move them to Plex library.

The process is:
1. Add & download torrent from qBittorrent Web UI using showrss.info feed
2. Convert .mkv to .mp4 if needed, using AAC and `-movflags faststart`
3. Rename file using FileBot
4. Move file to Plex library
5. Refresh Plex library
6. Send email notification
