from flask import Flask, request, send_file
import requests
from twilio.twiml.messaging_response import MessagingResponse
from PIL import Image, ImageOps
import io
import base64
import cv2
import threading
import os
import time
import sqlite3

app = Flask(__name__)

username = 'ACfc171cd799d4d5d5b4ea001e15a27cf2'
password = '6d526a2566ef2ba2bbe98984c7361022'

recipient_number = "+919385325779"

# Create a thread-local storage to hold database connections
thread_local = threading.local()
# SQLite database file
db_file = 'user_stats.db'


def get_connection():
    # Get or create a database connection for the current thread
    if not hasattr(thread_local, 'connection'):
        thread_local.connection = sqlite3.connect(db_file)
    return thread_local.connection


def record_user_statistics(user_number):
    global conn
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if the user number is already in the database
        cursor.execute('SELECT * FROM user_statistics WHERE user_number=?', (user_number,))
        user_data = cursor.fetchone()

        if user_data is None:
            # If the user is not in the database, insert a new record
            cursor.execute('INSERT INTO user_statistics (user_number, call_count) VALUES (?, 1)', (user_number,))
        else:
            # If the user is in the database, update the call count
            updated_count = user_data[1] + 1
            cursor.execute('UPDATE user_statistics SET call_count=? WHERE user_number=?', (updated_count, user_number))

        # Commit the changes to the database
        conn.commit()

    except Exception as e:
        print("Error processing database:", str(e))
    finally:
        if conn:
            conn.close()  # Close the connection in the 'finally' block


# Function to fetch user statistics and send a WhatsApp message
def send_user_statistics_via_whatsapp(user_number, recipient_whatsapp_number):
    global conn
    try:
        from twilio.rest import Client
        account_sid = username
        auth_token = password

        # Initialize Twilio client
        client = Client(account_sid, auth_token)
        # Connect to the SQLite database
        conn = sqlite3.connect('user_stats.db')
        cursor = conn.cursor()

        # Fetch the user statistics
        cursor.execute('SELECT call_count FROM user_statistics WHERE user_number=?', (user_number,))
        user_data = cursor.fetchone()

        if user_data is not None:
            call_count = user_data[0]
            message = f"User {user_number} has used the service {call_count} times."

            # Send the message via WhatsApp using Twilio
            client.messages.create(
                from_='whatsapp:+14155238886',
                body=message,
                to=f'whatsapp:{recipient_whatsapp_number}'
            )
    except Exception as e:
        print("Error sending WhatsApp message:", str(e))
    finally:
        conn.close()  # Close the database connection


def process_image_and_send_response(image_data, msg, user_number):
    try:
        # Open the image using PIL
        image = Image.open(io.BytesIO(image_data))

        record_user_statistics(user_number)

        # Process the image and get the result
        image_with_count, num = count(image)

        # close_database_connection()
        results_folder = "results"
        os.makedirs(results_folder, exist_ok=True)  # Create the "results" folder if it doesn't exist

        # Save the processed image with a unique filename (e.g., based on a timestamp)
        timestamp = time.strftime("%Y%m%d%H%M%S")
        result_image_filename = f"{results_folder}/result_{timestamp}.png"
        image_with_count.save(result_image_filename, format='PNG')

        # media_url = f"https://f338-117-255-123-122.ngrok-free.app/{result_image_filename}"
        media_url = f"https://whatsapphandler.onrender.com/{result_image_filename}"
        send_whatsapp_response(user_number, media_url, num)
        send_user_statistics_via_whatsapp(user_number, recipient_number)
    except Exception as e:
        print("Error processing image:", str(e))
        return "An error occurred while processing the image."


# Function to compress an image
def compress_image(image, quality=70):
    # Ensure that the image is in RGB mode
    if image.mode != 'RGB':
        image = image.convert('RGB')
    # Compress the image using the specified quality factor
    compressed_image = ImageOps.exif_transpose(image)
    compressed_image = compressed_image.convert('RGB')
    img_byte_array = io.BytesIO()
    compressed_image.save(img_byte_array, format='JPEG', quality=quality)
    img_byte_array.seek(0)

    return Image.open(img_byte_array)


# Function to send a WhatsApp response using Twilio
def send_whatsapp_response(user_number, media_url, cellcount):
    from twilio.rest import Client
    num = '+' + user_number
    # Your Twilio Account SID and Auth Token
    account_sid = username
    auth_token = password

    # Initialize Twilio client
    client = Client(account_sid, auth_token)

    # Send a WhatsApp message
    message = client.messages.create(
        media_url=[media_url],
        body=cellcount,
        from_='whatsapp:+14155238886',  # Your Twilio WhatsApp number
        to=f'whatsapp:{num}'
    )


def crop_image(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    th, threshed = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)

    # (2) Morph-op to remove noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    morphed = cv2.morphologyEx(threshed, cv2.MORPH_CLOSE, kernel)

    # (3) Find the max-area contour
    cnts = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
    cnt = sorted(cnts, key=cv2.contourArea)[-1]

    # (4) Crop and save it
    x, y, w, h = cv2.boundingRect(cnt)
    dst = image[y:y + h, x:x + w]
    return dst


def respond(message):
    response = MessagingResponse()
    response.message(message)
    return str(response)


def count(image):
    # The URL of the endpoint
    print('hi')
    url = "https://cellcounter.onrender.com/detect"
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    data = {
        'image': base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    }

    # Send the HTTP POST request and receive the response
    response = requests.post(url, json=data, timeout=240)
    if response.status_code == 200:

        data = response.json()
        # Get the Base64-encoded image data
        image_base64 = data['image']
        num = data['number']
        # Decode the Base64-encoded image data to bytes
        image_bytes = base64.b64decode(image_base64)
        # Open the image data as an Image object
        image = Image.open(io.BytesIO(image_bytes))
    else:
        print("It is ok ,All is Well", response.status_code)
    return image, num


@app.route("/test")
def wa_hello():
    return "Hello, World!"


@app.route('/results/<path:image_filename>')
def serve_image(image_filename):
    # Define the path to the directory where your images are stored locally
    image_directory = 'results'
    return send_file(f"{image_directory}/{image_filename}")


@app.route("/wasapresp", methods=['POST'])
def wa_sms_reply():
    """Respond to incoming calls with a simple text message."""
    # Fetch the message
    Fetch_msg = request.form
    print("Fetch_msg-->", Fetch_msg)
    num = ''
    resp = MessagingResponse()
    reply = resp.message()

    try:  # Storing the file that user send to the Twilio whatsapp number in our computer
        msg_url = request.form.get('MediaUrl0')  # Getting the URL of the file
        print("msg_url-->", msg_url)
        msg_ext = request.form.get('MediaContentType0')  # Getting the extension for the file
        print("msg_ext-->", msg_ext)
        ext = msg_ext.split('/')[-1]
        print("ext-->", ext)
        user_number = request.form.get('WaId')

        if msg_url is not None:
            json_path = requests.get(msg_url, auth=(username, password))
            print(json_path.status_code)
            if json_path.status_code == 200:
                # Check if the response content is an image
                if json_path.headers.get('content-type') == 'image/jpeg':
                    # Read the image data
                    image_data = json_path.content
                    msg = 'image count'

                    # Start a new thread to process the image and send a response
                    image_processing_thread = threading.Thread(
                        target=process_image_and_send_response,
                        args=(image_data, msg, user_number)
                    )
                    image_processing_thread.start()
                else:
                    print("Response content is not an image.")
            else:
                print(f"Request failed with status code {json_path.status_code}")
            # filename = msg_url.split('/')[-1]
            # open(filename + "." + ext, 'wb').write(json_path.content)  # Storing the file
    except:
        print("no url-->>")
    msg = request.form.get('Body').lower()  # Reading the messsage from the whatsapp

    print("msg-->", msg)

    # Create reply
    # Text response
    if msg == "hi":
        reply.body("Hello")

    # Image response
    elif msg == "image":
        reply.media(
            'https://static.wikia.nocookie.net/characterprofile/images/c/c8/BotW_Link.png/revision/latest?cb'
            '=20170306180639',
            caption="jj ccp")
    # File response`
    elif msg == "file":
        reply.media('http://www.africau.edu/images/default/sample.pdf')

    # resp = MessagingResponse()
    # resp.message("You said: {}".format(msg))
    else:
        reply.body("Your image is being processed by our AI agent ,please wait - you will receive the results shortly.")

    return str(resp)


# Close the database connection when done
# def close_database_connection():
#     conn.close()


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=True)

# https://d168-117-255-122-210.ngrok-free.app/1693488871587.jpeg
