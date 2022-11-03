import os
from socket import *
import threading
from time import sleep
import pickle
from datetime import datetime
from collections import deque

ip = gethostbyname(gethostname())
server = socket(AF_INET, SOCK_STREAM)
print(ip)
server.bind((ip, 50005))
server.listen()
FILESERVER = 'files'
if not os.path.exists(FILESERVER):
    os.mkdir(FILESERVER)

registrated = {'SOME_GROUP': ['ADD USERNAMES', 'user1']}

clients = []
nicknames = []


def time():
    now = datetime.now()
    current_time = now.strftime("[%d-%m-%Y %H:%M:%S] ")
    return current_time


def privatemsg(message, client):
    try:
        sleep(0.10)
        end = b';$&nd/'
        dict_msg = pickle.dumps(message)
        client.send(dict_msg)
        client.send(end)
    except Exception as exc:
        print(f'privatemsg error: {exc}')


def broadcast(message):
    for client in clients:
        privatemsg(message, client)


def dirmaker(dir, subdir=None):
    logdir = os.path.join(FILESERVER, dir)
    if not os.path.exists(logdir):
        os.mkdir(logdir)
    if subdir:
        s_logdir = os.path.join(logdir, subdir)
        if not os.path.exists(s_logdir):
            os.mkdir(s_logdir)
        return s_logdir
    return logdir


def logger(dir, msg):
    try:
        log = os.path.join(dir, 'log')
        with open(log, 'a') as file:
            if os.stat(log).st_size != 0:
                file.writelines(f'\n{msg}')
            else:
                file.writelines(f'{msg}')
    except Exception as exc:
        print('logger error:', exc)


def handle(client):
    while True:
        try:
            rawmsg = client.recv(1024)
            print(rawmsg)
            msg_rc = b''
            end = b';$&nd/'
            while rawmsg != end:
                msg_rc += rawmsg
                rawmsg = client.recv(1024)
            if msg_rc:
                msg = pickle.loads(msg_rc)
                print('msg handle:', msg)
                timeappend = f'{time()}{msg[2]}'
                sender = nicknames[clients.index(client)]
                recipient = msg[1]
                msg[2] = timeappend
                if msg[0] == 'msgall':
                    logger(dirmaker('tab'), msg[2])
                    broadcast(msg)
                elif msg[0] == 'last':
                    dir = dirmaker(sender, recipient)
                    send_last(dir, client, recipient)
                elif msg[0] == 'privatemsg':
                    logger(dirmaker(recipient, sender), msg[2])
                    if recipient != sender:
                        logger(dirmaker(sender, recipient), msg[2])
                    if recipient in nicknames:
                        pmsg = ['privatemsg', sender, msg[2]]
                        privatemsg(pmsg,  clients[nicknames.index(recipient)])

        except Exception as exc:
            print('handle error:', exc)
            index = clients.index(client)
            clients.remove(client)
            client.close()
            nickname = nicknames[index]
            broadcast(['msgall', '', f'{nickname} left the chat'])
            nicknames.remove(nickname)
            break


def send_last(dir, client, companion):
    try:
        with open(os.path.join(dir, 'log'), 'r') as file:
            last_msgs = list(deque(file, 10))
        last_msgs_ed = []
        for idx, m in enumerate(last_msgs):
            if idx != (len(last_msgs) - 1):
                last_msgs_ed.append(m[0:-1])
            else:
                last_msgs_ed.append(m)
        if companion == 'tab':
            msg = ['msgall', 'hist', last_msgs_ed]
        else:
            msg = ['hist', companion, last_msgs_ed]
        privatemsg(msg, client)
    except Exception as exc:
        print('send_last error:', exc)


def receive():
    while True:
        client, address = server.accept()
        print(f'Connection to: {address}')

        msg = pickle.loads(client.recv(1024))
        print('msg to sort:', msg)
        if msg[0] == 'nickname':
            if msg[1] in nicknames:
                client.close()
            else:
                nickname = msg[1]
                nicknames.append(nickname)
                clients.append(client)
                print(f'New user nickname {nickname}')
                sleep(1)
                send_last(dirmaker('tab'), client, 'tab')
                broadcast(['msgall', '', f'{nickname} entered the chat'])
                sleep(0.02)
                all_users(client)
                sleep(0.1)
                nicklist_part()
                thread = threading.Thread(target=handle, args=(client,))
                thread.start()
        if msg[0] == 'file':
            filetread = threading.Thread(target=filereceive, args=(client,))
            filetread.start()

        if msg[0] == 'filerequest':
            fileshare_tread = threading.Thread(target=fileshare, args=(client,))
            fileshare_tread.start()


def fileshare(client):
    while True:
        try:
            msg_rc = client.recv(1024)
            tag_msg = pickle.loads(msg_rc)
            split = tag_msg[3].split('/')
            reqfile = os.path.join(FILESERVER, split[0], split[1], split[2])
            filesize = pickle.dumps(os.stat(reqfile).st_size)
            client.send(filesize)

            with open(reqfile, "rb") as file:
                filemsg = file.read(1024)
                while filemsg:
                    client.send(filemsg)
                    filemsg = file.read(1024)

            client.close()
            break
        except Exception as exc:
            print('fileshare error:', exc)
            client.close()
            break


def filereceive(client):
    while True:
        try:
            msg_rc = client.recv(1024)
            msg = pickle.loads(msg_rc)
            if msg[0] == 'tagmsg':
                sender = msg[1]
                recipient = msg[2]
                filename = msg[3]
                checksum = msg[4]
                print(sender, recipient, filename)
                path = dirmaker(recipient, sender)
                filename_path = os.path.join(path, filename)
                with open(filename_path, 'wb') as file:
                    data = client.recv(1024)
                    while data:
                        file.write(data)
                        data = client.recv(1024)
                if os.stat(filename_path).st_size == checksum:
                    print('file prinyat')
                    msg_tosend = f'{time()}{sender}: <a href="{recipient}/{sender}/{filename}">{filename}</a>'
                    if recipient == 'tab':
                        msg = ['msgall', '', msg_tosend]
                        print(msg_tosend)
                        logger(dirmaker('tab'), msg_tosend)
                        broadcast(msg)
                    else:
                        pmsg = ['privatemsg', recipient, msg_tosend]
                        pmsg2 = ['privatemsg', sender, msg_tosend]
                        privatemsg(pmsg, clients[nicknames.index(sender)])
                        logger(dirmaker(recipient, sender), msg_tosend)
                        if sender != recipient:
                            privatemsg(pmsg2, clients[nicknames.index(recipient)])
                            logger(dirmaker(sender, recipient), msg_tosend)
                else:
                    os.remove(filename_path)
                    print('file deleted')
                client.close()
                break

        except Exception as exc:
            print('filereceive error:', exc)
            client.close()
            break


def nicklist_part():
    nicklist = ['nicklist', nicknames]
    broadcast(nicklist)


def all_users(client):
    reglist = ['reglist', registrated]
    privatemsg(reglist, client)


def nicknamesander():
    while True:
        nicklist_part()
        sleep(15)


print(time())
users_thread = threading.Thread(target=nicknamesander)
users_thread.start()
print('Server started')

receive()
