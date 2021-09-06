# Utility to manage secure storage of confidential information,
# such as passwords. An encryption key is created based on the
# MAC of a stable machine in the local network.

# The plaintext file content is following the syntax defined
# at https://docs.python.org/3/library/configparser.html

# This mechanism is to prevent accidental leakage of
# confidential information via GitHub etc.

# The only thing to configure is the local IP address of the
# network card to be used as MAC provider
MAC_IP_ADDRESS = '192.168.1.10'

import base64
from getmac import get_mac_address
from cryptography.fernet import Fernet
import configparser
import os
import tempfile

def getEncryptionKey():
    mac = get_mac_address(ip=MAC_IP_ADDRESS)
    return base64.urlsafe_b64encode((bytes((mac+mac)[:32], 'utf-8')))


def encryptCreds(fileDecrypted, fileEncrypted):

    # read decrypted content from file
    with open(fileDecrypted, 'rb') as file:
        decryptedContent = file.read()

    # encrypt the content
    fernet = Fernet(getEncryptionKey())
    encryptedContent = fernet.encrypt(decryptedContent)

    # write encrypted data to file
    with open(fileEncrypted, 'wb') as encrypted_file:
        encrypted_file.write(encryptedContent)


def decryptCreds(fileDecrypted, fileEncrypted):

    # open the encrypted file, if it exists
    if os.path.exists(fileEncrypted):
        with open(fileEncrypted, 'rb') as enc_file:
            encryptedContent = enc_file.read()
    else:
        print(f"ERROR: {fileEncrypted} not found. Aborting...")
        exit(0)

    # decrypt the content
    fernet = Fernet(getEncryptionKey())
    decryptedContent = fernet.decrypt(encryptedContent)

    # save the content
    with open(fileDecrypted, 'wb') as dec_file:
        dec_file.write(decryptedContent)


def getValues():
    path = os.path.dirname(__file__)
    # Get platform-independant path
    fileEncrypted = findFirstFile('creds.encrypted', path)

    tmpFile = tempfile.NamedTemporaryFile()
    fileDecrypted = tmpFile.name
    tmpFile.close()

    decryptCreds(fileDecrypted, fileEncrypted)
    values = configparser.ConfigParser()
    values.read(fileDecrypted)
    os.remove(fileDecrypted)

    return values


def findFirstFile(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def main():
    path = os.path.dirname(__file__)
    # Get platform-independant path
    fileEncrypted = findFirstFile('creds.encrypted', path)

    tmpFile = tempfile.NamedTemporaryFile()
    fileDecrypted = tmpFile.name
    tmpFile.close()

    decryptCreds(fileDecrypted, fileEncrypted)

if __name__ == "__main__":
    main()
