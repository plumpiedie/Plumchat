import sys
from datetime import datetime
from time import sleep

from PyQt5.QtCore import QDate, QTime, Qt, QRect, QMetaObject, QPropertyAnimation, QThread, pyqtSignal, QSize, QEvent
from PyQt5.QtGui import QColor, QFont, QPixmap, QIcon, QTextCursor
from PyQt5.QtMultimedia import QSound
from PyQt5.QtWidgets import *
from socket import *
import os
import pickle


from mainwindow import *

import getpass


HOME_PATH = os.path.expanduser('~')
DESKTOP = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')  # ПРОВЕРИТЬ В ЛИНУКСЕ
USERFILES = os.path.join(HOME_PATH, 'PlumChat')
if not os.path.exists(USERFILES):
    os.mkdir(USERFILES)

IP_ADDRESS = '192.168.77.30'
PORT = 50005
window_obj = []
file_senders = {}
file_receivers = {}

class BlinkTab(QThread):
    blinkSignal = pyqtSignal(list)

    style_blink = 'orange'
    style_default = 'black'

    def __init__(self, companion):
        self.companion = companion
        super().__init__()

    def run(self):
        try:
            while True:
                self.blinkSignal.emit([self.companion, self.style_blink])
                sleep(0.7)
                self.blinkSignal.emit([self.companion, self.style_default])
                sleep(0.7)
        except Exception as exc:
            print('BlinkTab(QThread) error:', exc)

    def terminate(self):
        self.blinkSignal.emit([self.companion, self.style_default])
        super(BlinkTab, self).terminate()
        self.deleteLater()


class FileRequest(QThread):
    dwnldendSignal = pyqtSignal(str)
    r_max_progress = pyqtSignal(int)
    r_progress = pyqtSignal(int)

    def __init__(self, nickname, companion, anchor):
        self.nickname = nickname
        self.companion = companion
        self.anchor = anchor
        super().__init__()

    def run(self):
        try:
            print('rtag_msg', self.companion, self.anchor)
            tag_msg = ['rtag_msg', self.nickname, self.companion, self.anchor]
            self.fileclient = socket(AF_INET, SOCK_STREAM)
            self.fileclient.connect((IP_ADDRESS, PORT))
            self.fileclient.send(pickle.dumps(['filerequest', ]))
            file_receivers[self.companion] = self.fileclient
            sleep(2)
            self.fileclient.send(pickle.dumps(tag_msg))
            filesize = pickle.loads(self.fileclient.recv(1024))
            cicles = 0
            max_cicles = filesize // 1024
            self.r_max_progress.emit(max_cicles - 1)
            filename = self.anchor.split('/')[2]
            file = os.path.join(USERFILES, self.companion, filename)
            with open(file, 'wb') as self.file:
                data = self.fileclient.recv(1024)
                while data:
                    cicles += 1
                    self.r_progress.emit(cicles)
                    self.file.write(data)
                    data = self.fileclient.recv(1024)
            self.dwnldendSignal.emit(filename)
            file_receivers.pop(self.companion)
            print('скачан же', file)
            self.close()
        except Exception as exc:
            print('FileRequest(QThread) error:', exc)
            self.terminate()

    def terminate(self):
        super(FileRequest, self).terminate()
        if hasattr(self, 'file'):
            self.file.close()
        self.close()

    def close(self):
        if hasattr(self, 'fileclient'):
            self.fileclient.close()
        self.deleteLater()


class SendFile(QThread):
    laodendSignal = pyqtSignal(str)
    max_progress = pyqtSignal(int)
    progress = pyqtSignal(int)

    def __init__(self, tag_msg, res):
        self.tag_msg = tag_msg
        self.res = res
        super().__init__()

    def run(self):
        try:
            self.fileclient = socket(AF_INET, SOCK_STREAM)
            self.fileclient.connect((IP_ADDRESS, PORT))
            file_senders[self.tag_msg[2]] = self.fileclient
            self.fileclient.send(pickle.dumps(['file', ]))
            sleep(2)
            ptag_msg = pickle.dumps(self.tag_msg)
            self.fileclient.send(ptag_msg)
            # понадобится циклов
            max_cicles = os.stat(self.res[0]).st_size // 1024
            self.max_progress.emit(max_cicles - 1)
            cicles = 0

            with open(self.res[0], "rb") as self.file:
                filemsg = self.file.read(1024)
                try:
                    while filemsg:
                        cicles += 1
                        self.progress.emit(cicles)
                        self.fileclient.send(filemsg)
                        filemsg = self.file.read(1024)
                except Exception as exc:
                    print(exc)
            self.laodendSignal.emit(self.tag_msg[3])
            file_senders.pop(self.tag_msg[2])
            self.close()
        except Exception as exc:
            print('SendFile(QThread) error:', exc)
            self.terminate()

    def terminate(self):
        try:
            if hasattr(self, 'file'):
                self.file.close()
            super(SendFile, self).terminate()
            self.close()
        except Exception as exc:
            print(exc)

    def close(self):
        if hasattr(self, 'fileclient'):
            self.fileclient.close()
        self.deleteLater()


class Receive(QThread):
    threadSignal_all = pyqtSignal(list)
    threadSignal_pm = pyqtSignal(list)
    threadSignal_list = pyqtSignal(list)
    threadSignal_reg = pyqtSignal(dict)
    threadSignal_hist = pyqtSignal(list)

    def __init__(self, client):
        self.client = client
        super().__init__()

    def run(self):
        while True:
            try:
                # if dlgMain.connected:
                rawmsg = self.client.recv(1024)
                msg = b''
                end = b';$&nd/'
                while rawmsg != end:
                    msg += rawmsg
                    rawmsg = self.client.recv(1024)
                msg = self.rcv(msg)
                print('msg to sort:', msg)
                if msg[0] == 'msgall':
                    self.threadSignal_all.emit(msg)
                elif msg[0] == 'privatemsg':
                    self.threadSignal_pm.emit(msg)
                elif msg[0] == 'nicklist':
                    self.threadSignal_list.emit(msg[1])
                elif msg[0] == 'reglist':
                    self.threadSignal_reg.emit(msg[1])
                elif msg[0] == 'hist':
                    self.threadSignal_hist.emit(msg)
            except Exception as exc:
                print(f'Receive(QThread): error: {exc}')
                self.client.close()
                break

    def rcv(self, msg_rc):
        return pickle.loads(msg_rc)


class PopUp(QWidget):

    def __init__(self):
        super().__init__()
        QSound.play('popup.wav')
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setWindowFlag(Qt.Tool)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.move(QApplication.desktop().availableGeometry().width() - 200,
                  QApplication.desktop().availableGeometry().height() - 50)
        self.label = QLabel('___', self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet('''
            background-color: black;
            color: white;
            border-style: outset;
            border-width: 2px;
            border-radius: 10px;
            border-color: beige;
            font: bold 14px;
            min-width: 10em;
            padding: 6px;
        ''')

    def show(self):
        super().show()
        QSound.play('popup.wav')
        self.layout = QHBoxLayout(self)
        self.layout.addWidget(self.label)
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(2000)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()
        if self.windowOpacity() == 0.0:
            QWidget.hide(self)
        self.mouseReleaseEvent = lambda event: QWidget.hide(self)


class MainWindow(QMainWindow):


    def __init__(self):
        QMainWindow.__init__(self)
        self.nickname = getpass.getuser()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowFlag(Qt.FramelessWindowHint)

        # self.ui.cornerGrips = [QtWidgets.QSizeGrip(self) for i in range(4)]

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(50)
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(0)
        self.shadow.setColor(QColor(0, 92, 157, 550))
        self.ui.centralwidget.setGraphicsEffect(self.shadow)
        self.setWindowTitle('Plumchat_beta')

        self.ui.push_btn_menu.clicked.connect(lambda: self.togglemenu(250, True))

        # управления пунктами меню
        self.ui.menu_btn_1.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.page))
        self.ui.menu_btn_2.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.page_3))
        self.ui.menu_btn_3.clicked.connect(self.default_tree_style)
        #self.ui.menu_btn_3.clicked.connect(lambda: self.ui.stackedWidget.setCurrentWidget(self.ui.page_2))

        # управление окном
        self.ui.frame_top.mouseMoveEvent = self.moveWindow
        self.ui.pushButton_4.clicked.connect(lambda: self.showMinimized())
        self.ui.pushButton_3.clicked.connect(lambda: self.restore_or_maximize_window())
        self.ui.pushButton_2.clicked.connect(lambda: self.close())
        # tray
        action_hide.triggered.connect(lambda: self.hide())
        action_show.triggered.connect(lambda: self.showNormal())

        # действия кнопок
        self.ui.label.setText(self.windowTitle())
        self.ui.plaintab.setPlaceholderText('Введите сообщение')
        self.ui.sendButton.clicked.connect(self.send_massage)
        # self.ui.tabWidget.setTabsClosable(True)
        self.ui.listWidget.itemDoubleClicked.connect(self.user_list_clicked)
        self.ui.tabWidget.tabCloseRequested.connect(self.close_tab)
        self.ui.tabWidget.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.ui.sendFiletab.clicked.connect(self.send_file)

        # надо переработать
        self.ui.exit_btn.clicked.connect(self.exit)

        # часть для коннекта (сейчас не работает по сути)
        self.ui.plaintab.setDisabled(True)
        self.ui.listWidget.setDisabled(True)
        self.ui.sendButton.setDisabled(True)
        #self.ui.tabWidget.setDisabled(True)

        # создание словаря пользователй
        self.reg_usrs = {}
        self.online_usrs = []

        self.connected = False
        self.connection()

        # изменение поведения кнопки enter
        self.ui.plaintab.installEventFilter(self, )

        self.ui.tabWidget.setMovable(True)
        self.ui.tabWidget.tabBarClicked.connect(self.tabbarclicked)

        self.ui.brawtab.setOpenLinks(False)
        self.ui.brawtab.anchorClicked.connect(self.anchor_clicked)
        QMetaObject.connectSlotsByName(self)

    def opened_tabs(self, tab):
        pass
    #  сделать открытие полсдених вкладок после включения

    def default_tree_style(self):

        self.ui.listWidget.setStyleSheet("color: rgb(201, 178, 202);\n"
                                         "border-left: 1px solid rgb(195, 172, 193);\n"
                                         "border-top: none")
        try:
            for i in range(self.ui.listWidget.topLevelItemCount()):
                for y in range(self.ui.listWidget.topLevelItem(i).childCount()):
                    self.ui.listWidget.topLevelItem(i).child(y).setForeground(0, QColor(201, 178, 202))

        except Exception as exc:
            print(exc)
        # if self.ui.listWidget.findItems() is not None:
        #     for item in self.ui.listWidget.lower():
        #         print(item.objectName())

    def eventFilter(self, obj, event):
        try:
            if type(obj) is QPlainTextEdit and event.type() == QEvent.KeyPress:
                if (event.key() in (Qt.Key_Return, Qt.Key_Enter)) and (not event.modifiers() & Qt.ShiftModifier):
                    self.send_massage()
                    return True
            return super().eventFilter(obj, event)
        except Exception as exc:
            print(exc)

    def create_list(self, reg_usrs):
        try:
            self.reg_usrs = reg_usrs
            self.default_tree_style()
            for top, i in enumerate(reg_usrs.keys()):
                item_0 = QTreeWidgetItem(self.ui.listWidget)
                item_0.setForeground(0, QtGui.QBrush((QColor('color: rgb(44, 22, 35)'))))
                self.ui.listWidget.topLevelItem(top).setText(0, i)
                for low, y in enumerate(reg_usrs[i]):
                    item_1 = QTreeWidgetItem(item_0)
                    self.ui.listWidget.topLevelItem(top).child(low).setText(0, y)
        except Exception as exc:
            print('create_list error:', exc)

    def anchor_clicked(self, anchor):
        try:
            companion = self.ui.tabWidget.currentWidget().objectName()
            companion_folder = os.path.join(USERFILES, companion)
            if not os.path.exists(os.path.join(companion_folder)):
                os.mkdir(companion_folder)
            stranchor = anchor.toString()
            file = stranchor.split('/')
            filename = file[2]
            self.filelocation = os.path.join(companion_folder, filename)
            if os.path.exists(self.filelocation):
                os.startfile(self.filelocation)
            else:
                self.thread_file_request = FileRequest(self.nickname, companion, stranchor)
                self.thread_file_request.setObjectName(f'thread_file_request{companion}')
                self.thread_file_request.setParent(self.ui.tabWidget)
                self.thread_file_request.start()
                print(self.thread_file_request.objectName())
                self.r_barui = MyBar()
                self.r_barui.setupUi(self)
                r_barname = f'r_bar{companion}'
                globals()[r_barname] = QtWidgets.QProgressBar(self.r_barui.barframe)
                globals()[r_barname].setObjectName(f'bar{companion}')
                globals()[r_barname].setFormat('Скачивание...%p%')
                globals()[r_barname].setAlignment(Qt.AlignHCenter)
                self.r_barui.barlayout.insertWidget(0, globals()[r_barname])
                self.ui.tabWidget.findChild(QWidget, f'{companion}').layout().addWidget(self.r_barui.barframe)
                self.r_barui.cancelbtn.setObjectName((f'r_canbtn{companion}'))
                self.r_barui.cancelbtn.clicked.connect(lambda: self.cancel_filereceive(companion, self.filelocation))
                self.r_barui.barframe.setObjectName(f'r_barframe{companion}')
                self.thread_file_request.r_max_progress.connect(lambda p: globals()[r_barname].setMaximum(p))
                self.thread_file_request.r_progress.connect(lambda p: globals()[r_barname].setValue(p))
                self.thread_file_request.dwnldendSignal.connect(lambda: self.ui.tabWidget.findChild(QWidget, f'r_barframe{companion}').deleteLater())
        except Exception as exc:
            print('anchor_clicked error:', exc)

    def cancel_filereceive(self, companion, filelocation):
        try:
            thread = self.ui.tabWidget.findChild(QThread, f'thread_file_request{companion}')
            thread.terminate()
            self.ui.tabWidget.findChild(QWidget, f'r_barframe{companion}').deleteLater()
            if file_receivers[companion]:
                del file_receivers[companion]
            os.remove(filelocation)
        except Exception as exc:
            print(exc)

    def createtab(self, companion, clicked=False):
        try:
            self.ui.newtab = QWidget(self.ui.brawtab)
            self.ui.newtab.setObjectName(companion)
            self.ui.newtabframe = QtWidgets.QFrame(self.ui.newtab)
            self.ui.newtabframe.setFrameShape(QtWidgets.QFrame.NoFrame)
            self.ui.newtabframe.setFrameShadow(QtWidgets.QFrame.Raised)
            self.ui.newtablayout = QtWidgets.QVBoxLayout(self.ui.newtabframe)
            self.ui.newtablayout.setContentsMargins(0, 0, 0, 0)
            self.ui.newtablayout.setSpacing(0)
            self.ui.newtablayout.setObjectName("newtablayout")
            self.ui.newtablayout_2 = QtWidgets.QVBoxLayout(self.ui.newtab)
            self.ui.newtablayout_2.setContentsMargins(0, 0, 0, 0)
            self.ui.newtablayout_2.setSpacing(0)
            self.ui.msg_browser = QtWidgets.QTextBrowser(self.ui.newtabframe)
            self.ui.msg_browser.setObjectName(f'braw{companion}')
            self.ui.msg_browser.setStyleSheet("border: none")
            self.ui.plaintab = QtWidgets.QPlainTextEdit(self.ui.newtabframe)
            self.ui.plaintab.setMinimumSize(QtCore.QSize(0, 20))
            self.ui.plaintab.setMaximumSize(QtCore.QSize(16777215, 40))
            self.ui.plaintab.setObjectName(f'plain{companion}')
            self.ui.plaintab.setPlaceholderText('Введите сообщение')
            self.ui.plaintab.installEventFilter(self)
            self.ui.newtablayout_2.addWidget(self.ui.newtabframe)
            self.ui.newtablayout.addWidget(self.ui.msg_browser)

            self.ui.tabWidget.addTab(self.ui.newtab, companion)
            if clicked:
                self.ui.tabWidget.setCurrentWidget(self.ui.tabWidget.findChild(QWidget, companion))
            self.frame_5 = QtWidgets.QFrame(self.ui.newtabframe)
            self.frame_5.setFrameShape(QtWidgets.QFrame.NoFrame)
            self.frame_5.setFrameShadow(QtWidgets.QFrame.Raised)
            self.frame_5.setObjectName("frame_5")
            self.verticalLayout_6 = QtWidgets.QVBoxLayout(self.frame_5)
            self.verticalLayout_6.setContentsMargins(0, 0, 0, 0)
            self.verticalLayout_6.setSpacing(0)
            self.verticalLayout_6.setObjectName("verticalLayout_6")
            self.frame_4 = QtWidgets.QFrame(self.frame_5)
            self.frame_4.setMinimumSize(QtCore.QSize(0, 20))
            self.frame_4.setStyleSheet("color: rgb(44, 22, 35);\n"
                                       "border-left: 1px solid rgb(195, 172, 193);\n"
                                       "border-top: none")
            self.frame_4.setFrameShape(QtWidgets.QFrame.NoFrame)
            self.frame_4.setFrameShadow(QtWidgets.QFrame.Raised)
            self.frame_4.setObjectName("frame_4")
            self.horizontalLayout_8 = QtWidgets.QHBoxLayout(self.frame_4)
            self.horizontalLayout_8.setContentsMargins(0, 0, 0, 0)
            self.horizontalLayout_8.setSpacing(0)
            self.horizontalLayout_8.setObjectName("horizontalLayout_8")
            self.sendFile = QtWidgets.QPushButton("Файл", self.frame_4)
            sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Maximum)
            sizePolicy.setHorizontalStretch(0)
            sizePolicy.setVerticalStretch(0)
            sizePolicy.setHeightForWidth(self.sendFile.sizePolicy().hasHeightForWidth())
            self.sendFile.setSizePolicy(sizePolicy)
            self.sendFile.setObjectName(f'sendFile{companion}')
            self.sendFile.setMinimumSize(QtCore.QSize(40, 20))
            self.sendFile.setMaximumSize(QtCore.QSize(16777215, 16777215))
            self.sendFile.setStyleSheet("QPushButton {\n"
                                        "    color: rgb(230, 235, 238);\n"
                                        "    background-color: rgb(120, 67, 111);\n"
                                        "    border: 0px solid;\n"
                                        "    border-right: 1px solid rgb(195, 172, 193);\n"
                                        "}\n"
                                        "QPushButton:hover{\n"
                                        "    background-color: rgb(203, 151, 174);\n"
                                        "}\n"
                                        "QPushButton:pressed{\n"
                                        "  background-color: rgb(154, 138, 173);\n"
                                        "}\n"
                                        "\n"
                                        "")
            self.horizontalLayout_8.addWidget(self.sendFile)
            self.emo = QtWidgets.QPushButton("Эмо", self.frame_4)
            sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
            sizePolicy.setHorizontalStretch(0)
            sizePolicy.setVerticalStretch(0)
            sizePolicy.setHeightForWidth(self.emo.sizePolicy().hasHeightForWidth())
            self.emo.setSizePolicy(sizePolicy)
            self.emo.setMinimumSize(QtCore.QSize(40, 20))
            self.emo.setMaximumSize(QtCore.QSize(16777215, 16777215))
            self.emo.setStyleSheet("QPushButton {\n"
                                   "    color: rgb(230, 235, 238);\n"
                                   "    background-color: rgb(120, 67, 111);\n"
                                   "    border: 0px solid;\n"
                                   "\n"
                                   "}\n"
                                   "QPushButton:hover{\n"
                                   "    background-color: rgb(203, 151, 174);\n"
                                   "}\n"
                                   "QPushButton:pressed{\n"
                                   "  background-color: rgb(154, 138, 173);\n"
                                   "}\n"
                                   "\n"
                                   "")
            self.emo.setObjectName("emo")
            self.horizontalLayout_8.addWidget(self.emo)
            self.verticalLayout_6.addWidget(self.frame_4, 0, QtCore.Qt.AlignLeft)
            self.ui.newtablayout.addWidget(self.frame_5)
            self.ui.newtablayout.addWidget(self.ui.plaintab)
            self.sendFile.clicked.connect(self.send_file)
            self.ui.msg_browser.setOpenLinks(False)
            self.ui.msg_browser.anchorClicked.connect(self.anchor_clicked)
            self.last_msgs(companion)
            index = self.ui.tabWidget.indexOf(self.ui.newtab)
            if self.ui.tabWidget.widget(index).objectName() in self.online_usrs:
                self.ui.tabWidget.setTabIcon(index, QtGui.QIcon('green.svg'))
            else:
                self.ui.tabWidget.setTabIcon(index, QtGui.QIcon('grey.svg'))

        except Exception as exc:
            print(exc)

    def last_msgs(self, companion):
        msg = ['last', companion, '']
        self.msg_sender(msg)

    def close_tab(self, tab):
        try:

            tab_obj = self.ui.tabWidget.widget(tab)
            companion = tab_obj.objectName()
            self.delete_blink_tread(companion)
            if self.ui.tabWidget.findChild(QThread, f'thread_file{companion}'):
                self.cancel_filesend(companion)
            if self.ui.tabWidget.findChild(QThread, f'thread_file_request{companion}'):
                self.cancel_filereceive(companion, self.filelocation)
            tab_obj.deleteLater()
        except Exception as exc:
            print('close tab error:', exc)

    def append_browser(self, companion, text):
        searchbrowser = self.ui.tabWidget.findChild(QWidget, f'braw{companion}')
        searchbrowser.moveCursor(QTextCursor.End)
        searchbrowser.append('')
        searchbrowser.insertHtml(text)

    def user_list_clicked(self, user):
        try:
            user = QTreeWidgetItem.text(user, 0)
            if user in self.reg_usrs.keys():
                pass
            else:
                if self.ui.tabWidget.findChild(QWidget, user):
                    self.ui.tabWidget.setCurrentWidget(self.ui.tabWidget.findChild(QWidget, user))
                else:
                    self.createtab(user, clicked=True)
        except Exception as exc:
            print('user_list_clicked error', exc)

    def mouseDoubleClickEvent(self, event):
        self.restore_or_maximize_window()

    def mousePressEvent(self, event):
        self.clickPosition = event.globalPos()

    def moveWindow(self, e):
        if self.isMaximized() == False:  # Not maximized
            if e.buttons() == Qt.LeftButton:
                self.move(self.pos() + e.globalPos() - self.clickPosition)
                self.clickPosition = e.globalPos()
                e.accept()

    def restore_or_maximize_window(self):
        try:
            if self.isMaximized():
                self.showNormal()
                # Change Icon
                # self.ui.menu_btn_3.setIcon(QtGui.QIcon(u":/icons/icons/maximize-2.svg"))
            else:
                self.showMaximized()
                # Change Icon
                # self.ui.menu_btn_3.setIcon(QtGui.QIcon(u":/icons/icons/minimize-2.svg"))
        except Exception as exc:
            print(exc)

    def time(self):
        now = datetime.now()
        current_time = now.strftime("[%d-%m-%Y %H:%M:%S] ")
        return current_time

    def togglemenu(self, maxWidth, enable):
        if enable:

            # GET WIDTH
            width = self.ui.frame_left_menu.width()
            maxExtend = maxWidth
            standard = 70

            # SET MAX WIDTH
            if width == 70:
                widthExtended = maxExtend
            else:
                widthExtended = standard

            # ANIMATION
            self.animation = QPropertyAnimation(self.ui.frame_left_menu, b"minimumWidth")
            self.animation.setDuration(400)
            self.animation.setStartValue(width)
            self.animation.setEndValue(widthExtended)
            self.animation.setEasingCurve(QtCore.QEasingCurve.InOutQuart)
            self.animation.start()

    def popup(self, msg):
        if not self.isActiveWindow():
            popup = PopUp()
            popup.label.setText(msg)
            popup.show()

    def pm_chat_append(self, msg):
        try:
            companion = msg[1]
            searchtab = self.ui.tabWidget.findChild(QWidget, companion)
            if searchtab is None:
                self.createtab(companion)
                self.pm_chat_append(msg)
            else:
                if companion != self.ui.tabWidget.currentWidget().objectName():
                    blink_thread_name = f'blink_thread{companion}'
                    if self.ui.tabWidget.findChild(QThread, blink_thread_name) is None:
                        self.blinking_thread = BlinkTab(companion)
                        self.blinking_thread.setParent(self.ui.tabWidget)
                        self.blinking_thread.setObjectName(blink_thread_name)
                        self.blinking_thread.start()
                        self.blinking_thread.blinkSignal.connect(self.blinking)
                self.append_browser(companion, msg[2])
                self.popup(msg[2])
        except Exception as exc:
            print('pm_chat_append error:', exc)

    def tabbarclicked(self, tab_index):
        try:
            companion = self.ui.tabWidget.widget(tab_index).objectName()
            self.delete_blink_tread(companion)
        except Exception as exc:
            print('tabbarclicked error:', exc)

    def delete_blink_tread(self, companion):
        thread = self.ui.tabWidget.findChild(QThread, f'blink_thread{companion}')
        if thread is not None:
            thread.terminate()

    def blinking(self, tabFlex):
        searchtab = self.ui.tabWidget.findChild(QWidget, tabFlex[0])
        index = self.ui.tabWidget.indexOf(searchtab)
        self.ui.tabWidget.tabBar().setTabTextColor(index, QColor(tabFlex[1]))

    def pm_history(self, msg):
        try:
            companion = msg[1]
            for m in msg[2]:
                self.append_browser(companion, m)
        except Exception as exc:
            print(exc)

    def all_chat_append(self, msg):
        try:
            if msg[1] == 'hist':
                for m in msg[2]:
                    self.append_browser('tab', m)
            else:
                self.append_browser('tab', msg[2])
                self.popup(msg[2])
        except Exception as exc:
            print('all_chat_append', exc)

    def connection(self):
        self.client = socket(AF_INET, SOCK_STREAM)
        self.client.connect((IP_ADDRESS, PORT))
        self.connected = True
        nickname = ['nickname', self.nickname]
        self.msg_sender(nickname)
        self.ui.plaintab.setDisabled(False)
        self.ui.sendButton.setDisabled(False)
        self.ui.listWidget.setDisabled(False)
        self.ui.tabWidget.setDisabled(False)

        self.thread_receive = Receive(self.client)
        self.thread_receive.start()
        self.thread_receive.threadSignal_all.connect(self.all_chat_append)
        self.thread_receive.threadSignal_pm.connect(self.pm_chat_append)
        self.thread_receive.threadSignal_list.connect(self.user_list_online)
        self.thread_receive.threadSignal_reg.connect(self.create_list)
        self.thread_receive.threadSignal_hist.connect(self.pm_history)

    def send_massage(self):
        try:
            companion = self.ui.tabWidget.currentWidget().objectName()
            textbox = self.ui.tabWidget.findChild(QWidget, f'plain{companion}')
            text_msg = textbox.toPlainText()
            if text_msg:
                msg = f'{self.nickname}: {text_msg}'
                msg = msg.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                print(msg)
                if len(msg) < 1000:
                    if companion == 'tab':
                        msgall = ['msgall', companion, msg]
                        self.msg_sender(msgall)
                    else:
                        privatemsg = ['privatemsg', companion, msg]
                        if companion != self.nickname:
                            self.append_browser(companion, f'{self.time()}{msg}')
                        self.msg_sender(privatemsg)
                    textbox.setPlainText(None)
                else:
                    QMessageBox.critical(self, 'Уведомление', 'Количество введённых символов не должно превышать 1000')
        except Exception as exc:
            print(exc)

    def msg_sender(self, msg):
        dict_msg = pickle.dumps(msg)
        end = b';$&nd/'
        self.client.send(dict_msg)
        self.client.send(end)

    def send_file(self):
        try:
            res = QFileDialog.getOpenFileName(directory=DESKTOP, caption='Выберите файл для отправки')
            if res[0]:

                companion = self.ui.tabWidget.currentWidget().objectName()
                self.ui.tabWidget.findChild(QWidget, f'sendFile{companion}').setDisabled(True)
                # 0 - tag, 1 - nickname, 2 - to, 3 - filename, 4 - checksum
                tag_msg = ['tagmsg', self.nickname, companion, os.path.basename(res[0]), os.stat(res[0]).st_size]

                self.thread_file = SendFile(tag_msg, res)
                self.thread_file.setObjectName(f'thread_file{companion}')
                self.thread_file.setParent(self.ui.tabWidget)
                self.thread_file.start()
                print(self.thread_file.objectName())
                self.barui = MyBar()
                self.barui.setupUi(self)
                barname = f'bar{companion}'
                globals()[barname] = QtWidgets.QProgressBar(self.barui.barframe)
                globals()[barname].setObjectName(f'bar{companion}')
                globals()[barname].setFormat('Выгрузка...%p%')
                globals()[barname].setAlignment(Qt.AlignHCenter)
                self.barui.barlayout.insertWidget(0, globals()[barname])
                self.ui.tabWidget.findChild(QWidget, f'{companion}').layout().addWidget(self.barui.barframe)
                self.barui.cancelbtn.setObjectName((f'canbtn{companion}'))
                self.barui.cancelbtn.clicked.connect(lambda: self.cancel_filesend(companion))
                self.barui.barframe.setObjectName(f'barframe{companion}')
                self.thread_file.laodendSignal.connect(lambda p: self.progressbar(p, companion))
                self.thread_file.max_progress.connect(lambda p: (globals()[barname]).setMaximum(p))
                self.thread_file.progress.connect(lambda p: (globals()[barname]).setValue(p))
        except Exception as exc:
            print('send_file', exc)

    def progressbar(self, filename, companion):
        try:
            self.append_browser(companion, f'Отправлен файл: {os.path.basename(filename)}')
            self.ui.tabWidget.findChild(QWidget, f'barframe{companion}').deleteLater()
            self.ui.tabWidget.findChild(QWidget, f'sendFile{companion}').setDisabled(False)
        except Exception as exc:
            print(exc)

    def cancel_filesend(self, companion):
        try:
            thread = self.ui.tabWidget.findChild(QThread, f'thread_file{companion}')
            thread.terminate()
            self.ui.tabWidget.findChild(QWidget, f'barframe{companion}').deleteLater()
            if file_senders[companion]:
                file_senders.pop(companion).close()
            self.ui.tabWidget.findChild(QWidget, f'sendFile{companion}').setDisabled(False)
        except Exception as exc:
            print('cancel_filesend error:', exc)

    def disconnect(self):
        self.client.close()
        self.ui.plaintab.setDisabled(True)
        self.ui.sendButton.setDisabled(True)
        # self.discon_btn.setDisabled(True)
        self.ui.listWidget.setDisabled(True)
        # self.connect_btn.setDisabled(False)

    def user_list_online(self, msg):
        try:
            self.online_usrs = msg
            self.default_tree_style()
            for i in range(self.ui.listWidget.topLevelItemCount()):
                self.ui.listWidget.topLevelItem(i).setForeground(0, QtGui.QBrush((QColor('color: rgb(44, 22, 35)'))))
            for user in msg:
                item = self.ui.listWidget.findItems(user, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive)[0]
                item.setForeground(0, QtGui.QBrush((QColor('color: rgb(44, 22, 35)'))))
                # для вкладок
                tabname = self.ui.tabWidget.findChild(QWidget, user)
                for index in range(1, self.ui.tabWidget.count()):
                    if self.ui.tabWidget.widget(index).objectName() in self.online_usrs:
                        self.ui.tabWidget.setTabIcon(index, QtGui.QIcon('green.svg'))
                    else:
                        self.ui.tabWidget.setTabIcon(index, QtGui.QIcon('grey.svg'))


        except Exception as exc:
            print('user_list_add error:', exc)

    def exit(self):
        if self.connected:
            self.client.close()
        QApplication.exit()


if __name__ == '__main__':
    app = QApplication(sys.argv)  # create app

    tray = QSystemTrayIcon(QIcon("plum.svg"), app)
    menu = QMenu()

    app.setQuitOnLastWindowClosed(False)
    action_hide = QAction("Hide Window")
    menu.addAction(action_hide)
    action_show = QAction("Show Window")
    menu.addAction(action_show)
    action_exit = QAction("Exit")
    action_exit.triggered.connect(app.exit)
    menu.addAction(action_exit)

    tray.setToolTip("PlumPieChat")
    tray.setContextMenu(menu)
    tray.show()
    dlgMain = MainWindow()
    dlgMain.show()

    sys.exit(app.exec_())
