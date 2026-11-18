import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave


SOURCE = Path(__file__).resolve().parents[1] / "avatar/media-player.py"
SPEC = importlib.util.spec_from_file_location("avatar_media", SOURCE)
MEDIA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEDIA)


class AvatarMediaTest(unittest.TestCase):
    def test_folder_lists_supported_files_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ("b.MP3", "A.flac", "notes.txt"):
                (folder / name).touch()
            (folder / "directory.wav").mkdir()
            self.assertEqual([path.name for path in MEDIA.music_files(folder)], ["A.flac", "b.MP3"])

    def test_mujawwad_catalogue_has_all_surahs_with_numbered_uris(self):
        self.assertEqual(len(MEDIA.SURAHS), 114)
        self.assertEqual(MEDIA.SURAHS[0], "الفاتحة")
        self.assertEqual(MEDIA.SURAHS[-1], "الناس")
        self.assertEqual(MEDIA.surah_uri(0), MEDIA.RECITATION + "001.mp3")
        self.assertEqual(MEDIA.surah_uri(113), MEDIA.RECITATION + "114.mp3")
        with self.assertRaises(IndexError):
            MEDIA.surah_uri(-1)

    def test_published_state_distinguishes_playback_from_selection(self):
        player = MEDIA.Player()
        player.state = MEDIA.Gio.SimpleAction.new_stateful(
            "now-playing", None, MEDIA.GLib.Variant("s", "none"))
        player.current = ("quran", 0)
        player.publish(True)
        self.assertEqual(player.state.get_state().get_string(), "quran")
        player.publish(False)
        self.assertEqual(player.current, ("quran", 0))
        self.assertEqual(player.state.get_state().get_string(), "none")

    def test_gstreamer_decodes_a_local_file_without_a_desktop(self):
        gst = MEDIA.Gst
        gst.init(None)
        player = gst.ElementFactory.make("playbin")
        sink = gst.ElementFactory.make("fakesink")
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "Short sample.wav"
            with wave.open(str(audio), "wb") as recording:
                recording.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                recording.writeframes(b"\0\0" * 400)
            player.props.flags = 0x02
            player.props.audio_sink = sink
            player.props.uri = audio.as_uri()
            try:
                player.set_state(gst.State.PLAYING)
                message = player.get_bus().timed_pop_filtered(
                    5 * gst.SECOND, gst.MessageType.ERROR | gst.MessageType.EOS)
                self.assertIsNotNone(message)
                self.assertEqual(message.type, gst.MessageType.EOS)
            finally:
                player.set_state(gst.State.NULL)
