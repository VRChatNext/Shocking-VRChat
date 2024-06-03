from pythonosc.udp_client import SimpleUDPClient
import time, random

ip = "127.0.0.1"
port = 9001

client = SimpleUDPClient(ip, port)  # Create client

# client.send_message("/avatar/parameters/Shock/Area1", 0.02)   # Send float message
# input()

# client.send_message("/avatar/parameters/ShockA1/a", [0.07,])  # Send message with int, float and string
# time.sleep(0.02)
# client.send_message("/avatar/parameters/ShockA1/b", [0.2,])  # Send message with int, float and string
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.3,])  # Send message with int, float and string
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.4,])  # Send message with int, float and string
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.5,])  # Send message with int, float and string
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.8,])  # Send message with int, float and string
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.9,])  # Send message with int, float and string
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.6,])  # Send message with int, float and string
# time.sleep(0.2)
for _ in range(30):
    client.send_message("/avatar/parameters/ShockB2/some/param", [random.random(),])  # Send message with int, float and string
    time.sleep(0.05)
for _ in range(200):
    client.send_message("/avatar/parameters/pcs/sps/pussy", [random.random(),])  # Send message with int, float and string
    time.sleep(0.05)
for _ in range(3):
    client.send_message("/avatar/parameters/ShockB2/some/param", [random.random(),])  # Send message with int, float and string
    time.sleep(0.05)