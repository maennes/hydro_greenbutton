# Utility to manage secure storage of confidential information,
# such as passwords. An encryption key is created based on the
# MAC of a stable machine in the local network.

# The plaintext file content is following the syntax defined
# at https://docs.python.org/3/library/configparser.html

# This mechanism is to prevent accidental leakage of
# confidential information via GitHub etc.

import base64
from getmac import get_mac_address
from cryptography.fernet import Fernet
import configparser
import os
import tempfile


def getEncryptionKey(MAC_IP_ADDRESS):
    # Get MAC address of network card identified by IP address
    mac = get_mac_address(ip=MAC_IP_ADDRESS)
    # Use the MAC address to construct a 32-byte token
    return base64.urlsafe_b64encode((bytes((mac+mac)[:32], 'utf-8')))


def encryptFileContent(fileWithDecryptedContent, fileWithEncryptedContent, MAC_IP_ADDRESS):

    # read decrypted content from file
    with open(fileWithDecryptedContent, 'rb') as df:
        decryptedContent = df.read()

    # encrypt the content
    fernet = Fernet(getEncryptionKey(MAC_IP_ADDRESS))
    encryptedContent = fernet.encrypt(decryptedContent)

    # write encrypted content to file
    with open(fileWithEncryptedContent, 'wb') as ef:
        ef.write(encryptedContent)


def decryptFileContent(fileWithDecryptedContent, fileWithEncryptedContent, MAC_IP_ADDRESS):

    # open the encrypted file, if it exists
    if os.path.exists(fileWithEncryptedContent):
        with open(fileWithEncryptedContent, 'rb') as enc_file:
            encryptedContent = enc_file.read()
    else:
        print(f"ERROR: {fileWithEncryptedContent} not found. Aborting...")
        exit(0)

    # decrypt the content
    fernet = Fernet(getEncryptionKey(MAC_IP_ADDRESS))
    decryptedContent = fernet.decrypt(encryptedContent)

    # save the content
    with open(fileWithDecryptedContent, 'wb') as dec_file:
        dec_file.write(decryptedContent)


def findFirstFile(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)


def getValues(MAC_IP_ADDRESS, ENCRYPTED_FILE):
    path = os.path.dirname(__file__)
    # Get platform-independant path of file
    fileWithEncryptedContent = findFirstFile(ENCRYPTED_FILE, path)

    tmpFile = tempfile.NamedTemporaryFile()
    fileWithDecryptedContent = tmpFile.name
    tmpFile.close()

    decryptFileContent(fileWithDecryptedContent, fileWithEncryptedContent, MAC_IP_ADDRESS)
    values = configparser.ConfigParser()
    values.read(fileWithDecryptedContent)
    os.remove(fileWithDecryptedContent)

    return values


def main():
    # Helper code to build encrypted file

    ENCRYPTED_FILE = 'creds.encrypted'
    path = os.path.dirname(__file__)
    # Get platform-independant path
    fileWithEncryptedContent = findFirstFile(ENCRYPTED_FILE, path)

    if fileWithEncryptedContent == None:
        print(f"File {ENCRYPTED_FILE} not found in {path}. Building new file...")

        # Build decrypted content and save to file
        decryptedContent ="[Hydro One]\nusername = me@gmail.com\npassword = ******\naccountid = 123456\nmeterid = 654321\n\n"
        decryptedContent +="[InfluxDB]\nusername = me@gmail.com\npassword = ******\nhost = 192.168.1.21\nport = 8086\ndatabase = ext"
        with open('creds.decrypted', 'wb') as df:
            df.write(bytes(decryptedContent, 'utf-8'))
        
        # Encrypt content and save to file
        encryptFileContent('creds.decrypted', 'creds.encrypted', '192.168.1.10')
        
        # Delete temporary file
        os.remove('creds.decrypted')

    else:
        print(f"You're good to go with {fileWithEncryptedContent}")

if __name__ == "__main__":
    main()
