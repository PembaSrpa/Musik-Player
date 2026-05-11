import sys
from PyQt6.QtWidgets import QApplication
from player import Player
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    player = Player()

    window = MainWindow(player)
    window.show()

    player.load_library()

    def on_library_done():
        window.restore_volume()

    player._loader.finished_loading.connect(on_library_done)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
