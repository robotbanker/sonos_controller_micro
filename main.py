from machine import Pin, ADC, I2C, deepsleep, SPI,PWM
import socket
import time
import network
import urequests
import framebuf
import math

# Wi-Fi credentials
SSID = "Pengussini Home 2.4Ghz"
PASSWORD = 'Puzzadipiedi89!'

BL = 13
DC = 8
RST = 12
MOSI = 11
SCK = 10
CS = 9

# Connect to Wi-Fi
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    
    while not wlan.isconnected():
        print("Connecting to Wi-Fi...")
        time.sleep(1)
    
    print("Connected to Wi-Fi")
    print(wlan.ifconfig())

def discover_sonos_devices(timeout=5):
    """
    Discovers Sonos devices on the network using SSDP.
    Implements a manual timeout mechanism compatible with MicroPython.
    Returns a list of Sonos device IPs.
    """
    MCAST_GRP = "239.255.255.250"
    MCAST_PORT = 1900
    SSDP_DISCOVER_MSG = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {MCAST_GRP}:{MCAST_PORT}\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        "MX: 1\r\n"
        "ST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n"
        "\r\n"
    )
    
    devices = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)  # Set socket to non-blocking mode
    sock.sendto(SSDP_DISCOVER_MSG.encode(), (MCAST_GRP, MCAST_PORT))
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            data, addr = sock.recvfrom(1024)
            if b"Sonos" in data:
                devices.append(addr[0])
        except OSError:
            # No data received, continue polling
            pass
    
    sock.close()
    print ("Hooked to SONOS. Speaker IP:")
    print (set(devices))
    return list(set(devices))

def send_sonos_command(ip, action, arguments=None):
    """
    Sends a UPnP command to the Sonos device.
    Supported actions: Play, Pause, SetVolume
    """
    control_url = f"http://{ip}:1400/MediaRenderer/AVTransport/Control"
    headers = {
        "Content-Type": "text/xml; charset=\"utf-8\"",
        "SOAPAction": f"\"urn:schemas-upnp-org:service:AVTransport:1#{action}\""
    }
    body = f"""
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        <s:Body>
            <u:{action} xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                <InstanceID>0</InstanceID>
                {arguments or ""}
            </u:{action}>
        </s:Body>
    </s:Envelope>
    """
    try:
        response = urequests.post(control_url, data=body, headers=headers)
        return response.status_code, response.text
    except Exception as e:
        return None, str(e)

def send_rendering_control_command(ip, action, arguments=None):
    """
    Sends a UPnP command to the Sonos RenderingControl service.
    Supported actions: GetVolume, SetVolume
    """
    control_url = f"http://{ip}:1400/MediaRenderer/RenderingControl/Control"
    headers = {
        "Content-Type": "text/xml; charset=\"utf-8\"",
        "SOAPAction": f"\"urn:schemas-upnp-org:service:RenderingControl:1#{action}\""
    }
    body = f"""
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        <s:Body>
            <u:{action} xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
                {arguments or ""}
            </u:{action}>
        </s:Body>
    </s:Envelope>
    """
    try:
        response = urequests.post(control_url, data=body, headers=headers)
        return response.status_code, response.text
    except Exception as e:
        return None, str(e)

def skip_to_next_song(ip):
    return send_sonos_command(ip, "Next", "")

def skip_to_prev_song(ip):
    return send_sonos_command(ip, "Previous", "")

def get_transport_state(ip):
    """
    Retrieves the current TransportState of the Sonos device.
    """
    arguments = """
    <InstanceID>0</InstanceID>
    """
    response = send_sonos_command(ip, "GetTransportInfo", arguments)
    
    if response[0] == 200:  # If the response status is OK
        # Extract TransportState from the response XML
        start_index = response[1].find('<CurrentTransportState>') + len('<CurrentTransportState>')
        end_index = response[1].find('</CurrentTransportState>')
        transport_state = response[1][start_index:end_index]
        return transport_state
    else:
        print("Error getting TransportState:", response)
        return None

def play_pause(ip):
    """
    Toggles between Play and Pause based on the current TransportState.
    """
    # Get the current transport state
    transport_state = get_transport_state(ip)
    if transport_state is None:
        print("Unable to retrieve transport state.")
        return None
    
    # Determine action based on transport state
    if transport_state == "PLAYING":
        # Pause if currently playing
        print("Currently playing. Pausing...")
        return send_sonos_command(ip, "Pause", "<InstanceID>0</InstanceID>")
    elif transport_state == "PAUSED_PLAYBACK":
        # Play if currently paused
        print("Currently paused. Playing...")
        return send_sonos_command(ip, "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>")
    else:
        print(f"Transport state is '{transport_state}'. No action taken.")
        return None

def get_album_image_url(ip):
    """
    Retrieves the album image URL for the currently playing track.
    """
    # Prepare the required arguments for GetPositionInfo
    arguments = """
    <InstanceID>0</InstanceID>
    """

    # Send the GetPositionInfo action to the AVTransport service
    response = send_sonos_command(ip, "GetPositionInfo", arguments)

    if response[0] == 200:  # If the response is OK
        # Extract the TrackMetaData from the response
        start_index = response[1].find('<TrackMetaData>') + len('<TrackMetaData>')
        end_index = response[1].find('</TrackMetaData>')
        track_metadata = response[1][start_index:end_index]

        if not track_metadata or track_metadata == "NOT_IMPLEMENTED":
            print("No metadata available for the current track.")
            return None

        # Decode the metadata (convert HTML entities to actual characters)
        track_metadata = track_metadata.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&amp;", "&")

        # Locate the <upnp:albumArtURI> tag in the metadata
        uri_start = track_metadata.find('<upnp:albumArtURI>')
        uri_end = track_metadata.find('</upnp:albumArtURI>')
        if uri_start != -1 and uri_end != -1:
            uri_start += len('<upnp:albumArtURI>')
            album_art_url = track_metadata[uri_start:uri_end].strip()

            # If the URL is valid, return it
            if album_art_url.startswith("https"):
                print (album_art_url)
                return album_art_url
            else:
                print("Invalid album art URI format.")
                return None
        else:
            print("Album art URI not found in metadata.")
            return None
    else:
        print("Error retrieving track metadata:", response)
        return None

def get_sonos_speaker_name(ip):
    """
    Retrieves the Sonos speaker's friendly name using the DeviceDescription.xml file.
    
    Args:
        ip (str): The IP address of the Sonos speaker.
    
    Returns:
        str: The friendly name of the Sonos speaker, or an error message.
    """
    try:
        url = f"http://{ip}:1400/xml/device_description.xml"
        response = urequests.get(url)
        if response.status_code == 200:
            xml_content = response.text
            # Parse the XML manually to extract the <friendlyName> tag
            start_tag = "<friendlyName>"
            end_tag = "</friendlyName>"
            start_index = xml_content.find(start_tag) + len(start_tag)
            end_index = xml_content.find(end_tag)
            if start_index > -1 and end_index > -1:
                return xml_content[start_index:end_index]
        return "Error: Unable to retrieve friendly name."
    except Exception as e:
        return f"Error: {str(e)}"

def get_current_volume(ip):
    """Gets the current volume level of the Sonos device."""
    # Define the arguments with InstanceID and Channel
    arguments = """
    <InstanceID>0</InstanceID>
    <Channel>Master</Channel>
    """
    
    # Send the command to the RenderingControl service
    response = send_rendering_control_command(ip, "GetVolume", arguments)
    
    if response[0] == 200:  # If the response status is OK
        # Extract volume from the response XML
        start_index = response[1].find('<CurrentVolume>') + len('<CurrentVolume>')
        end_index = response[1].find('</CurrentVolume>')
        current_volume = int(response[1][start_index:end_index])
        print (current_volume)
        return current_volume
    else:
        print("Error getting volume:", response)
        return None

def set_volume_up(ip, current_volume):
    """
    Increases the volume by 5 units, up to a maximum of 100.
    """
    # Calculate the new volume

    new_volume = current_volume + 1
    
    # Ensure the volume does not exceed 100
    if new_volume > 100:
        new_volume = 100
    
    # Prepare the SOAP arguments
    arguments = f"""
    <InstanceID>0</InstanceID>
    <Channel>Master</Channel>
    <DesiredVolume>{new_volume}</DesiredVolume>
    """
    
    # Send the new volume using the RenderingControl service
    return send_rendering_control_command(ip, "SetVolume", arguments)

def set_volume_down(ip, current_volume):
    """
    Increases the volume by 5 units, up to a maximum of 100.
    """
    # Calculate the new volume

    new_volume = current_volume - 1
    
    # Ensure the volume does not exceed 100
    if new_volume > 100:
        new_volume = 100
    
    # Prepare the SOAP arguments
    arguments = f"""
    <InstanceID>0</InstanceID>
    <Channel>Master</Channel>
    <DesiredVolume>{new_volume}</DesiredVolume>
    """
    
    # Send the new volume using the RenderingControl service
    return send_rendering_control_command(ip, "SetVolume", arguments)

class LCD_1inch3(framebuf.FrameBuffer):
    def __init__(self):
        self.width = 240
        self.height = 240
        
        self.cs = Pin(CS,Pin.OUT)
        self.rst = Pin(RST,Pin.OUT)
        
        self.cs(1)
        self.spi = SPI(1)
        self.spi = SPI(1,1000_000)
        self.spi = SPI(1,100000_000,polarity=0, phase=0,sck=Pin(SCK),mosi=Pin(MOSI),miso=None)
        self.dc = Pin(DC,Pin.OUT)
        self.dc(1)
        self.buffer = bytearray(self.height * self.width * 2)
        super().__init__(self.buffer, self.width, self.height, framebuf.RGB565)
        self.init_display()
        
        self.red   =   0x07E0
        self.green =   0x001f
        self.blue  =   0xf800
        self.white =   0xffff
        self.black =   0x0000
        
    def write_cmd(self, cmd):
        self.cs(1)
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def write_data(self, buf):
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(bytearray([buf]))
        self.cs(1)

    def init_display(self):
        """Initialize dispaly"""  
        self.rst(1)
        self.rst(0)
        self.rst(1)
        
        self.write_cmd(0x36)
        self.write_data(0x70)

        self.write_cmd(0x3A) 
        self.write_data(0x05)

        self.write_cmd(0xB2)
        self.write_data(0x0C)
        self.write_data(0x0C)
        self.write_data(0x00)
        self.write_data(0x33)
        self.write_data(0x33)

        self.write_cmd(0xB7)
        self.write_data(0x35) 

        self.write_cmd(0xBB)
        self.write_data(0x19)

        self.write_cmd(0xC0)
        self.write_data(0x2C)

        self.write_cmd(0xC2)
        self.write_data(0x01)

        self.write_cmd(0xC3)
        self.write_data(0x12)   

        self.write_cmd(0xC4)
        self.write_data(0x20)

        self.write_cmd(0xC6)
        self.write_data(0x0F) 

        self.write_cmd(0xD0)
        self.write_data(0xA4)
        self.write_data(0xA1)

        self.write_cmd(0xE0)
        self.write_data(0xD0)
        self.write_data(0x04)
        self.write_data(0x0D)
        self.write_data(0x11)
        self.write_data(0x13)
        self.write_data(0x2B)
        self.write_data(0x3F)
        self.write_data(0x54)
        self.write_data(0x4C)
        self.write_data(0x18)
        self.write_data(0x0D)
        self.write_data(0x0B)
        self.write_data(0x1F)
        self.write_data(0x23)

        self.write_cmd(0xE1)
        self.write_data(0xD0)
        self.write_data(0x04)
        self.write_data(0x0C)
        self.write_data(0x11)
        self.write_data(0x13)
        self.write_data(0x2C)
        self.write_data(0x3F)
        self.write_data(0x44)
        self.write_data(0x51)
        self.write_data(0x2F)
        self.write_data(0x1F)
        self.write_data(0x1F)
        self.write_data(0x20)
        self.write_data(0x23)
        
        self.write_cmd(0x21)

        self.write_cmd(0x11)

        self.write_cmd(0x29)

    def show(self):
        self.write_cmd(0x2A)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0xef)
        
        self.write_cmd(0x2B)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0xEF)
        
        self.write_cmd(0x2C)
        
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(self.buffer)
        self.cs(1)
    
    def draw_scaled_text(self, text, x, y, color, scale=2, max_width=None):
        """
        Draws scaled text on the display, wrapping to a new line without breaking words.

        Args:
            text (str): The text to draw.
            x (int): The x-coordinate of the top-left corner of the text.
            y (int): The y-coordinate of the top-left corner of the text.
            color (int): The color of the text.
            scale (int): The scaling factor (default is 2).
            max_width (int): The maximum width before wrapping to a new line (default is screen width).
        """
        if max_width is None:
            max_width = self.width  # Default to screen width if not specified

        char_width = 8 * scale  # Assume each character is 8 pixels wide
        char_height = 8 * scale  # Assume each character is 8 pixels tall
        temp_buf = framebuf.FrameBuffer(bytearray(128 * 16), 128, 16, framebuf.MONO_HLSB)

        # Track the current position for rendering text
        cur_x, cur_y = x, y
        space_width = char_width  # Width of a single space

        words = text.split()  # Split the text into words

        for word in words:
            # Calculate the width of the word
            word_width = len(word) * char_width

            # Check if the word fits on the current line
            if cur_x + word_width > max_width:
                cur_x = x  # Reset to the left margin
                cur_y += char_height  # Move down by one character height

                # Stop drawing if the text exceeds the display height
                if cur_y + char_height > self.height:
                    break

            # Render the word to the temp buffer
            for char in word:
                temp_buf.fill(0)
                temp_buf.text(char, 0, 0, 1)

                for j in range(16):  # Height of the temp buffer
                    for i in range(128):  # Width of the temp buffer
                        if temp_buf.pixel(i, j):  # Check if the pixel is set
                            for dy in range(scale):
                                for dx in range(scale):
                                    self.pixel(cur_x + i * scale + dx, cur_y + j * scale + dy, color)

                # Move the cursor to the right for the next character
                cur_x += char_width

            # Add a space between words
            cur_x += space_width

        self.show()
   
    def clear_screen(self, color=0x0000):
        """
        Clears the entire screen by filling it with the specified color.

        Args:
            color (int): The color to fill the screen with (default is black).
        """
        self.fill(color)  # Fill the screen with the specified color
        self.show()       # Refresh the display to apply changes

    def circle(self, x0, y0, radius, color):
        """
        Draws a circle on the display.

        Args:
            x0 (int): X-coordinate of the circle's center.
            y0 (int): Y-coordinate of the circle's center.
            radius (int): Radius of the circle.
            color (int): Color of the circle.
        """
        f = 1 - radius
        dx = 1
        dy = -2 * radius
        x = 0
        y = radius

        # Draw the initial points of the circle
        self.pixel(x0, y0 + radius, color)
        self.pixel(x0, y0 - radius, color)
        self.pixel(x0 + radius, y0, color)
        self.pixel(x0 - radius, y0, color)

        # Use the midpoint circle algorithm
        while x < y:
            if f >= 0:
                y -= 1
                dy += 2
                f += dy
            x += 1
            dx += 2
            f += dx

            # Draw the symmetric points of the circle
            self.pixel(x0 + x, y0 + y, color)
            self.pixel(x0 - x, y0 + y, color)
            self.pixel(x0 + x, y0 - y, color)
            self.pixel(x0 - x, y0 - y, color)
            self.pixel(x0 + y, y0 + x, color)
            self.pixel(x0 - y, y0 + x, color)
            self.pixel(x0 + y, y0 - x, color)
            self.pixel(x0 - y, y0 - x, color)

    def display_volume_level(self, volume, max_volume=100):
        """
        Displays the current volume level as a circular progress bar, filling clockwise from 12 o'clock.
        The circle changes color based on the volume:
        - Green for volume 0-40
        - Orange for volume 41-60
        - Red for volume 61-100

        Args:
            volume (int): Current volume level (0-100).
            max_volume (int): Maximum volume level (default is 100).
        """
        # Clear the screen
        self.fill(self.black)

        # Define circle parameters
        center_x = self.width // 2
        center_y = self.height // 2
        outer_radius = 60
        inner_radius = 40
        thickness = outer_radius - inner_radius

        # Determine the fill color based on volume
        if volume <= 40:
            fill_color = self.green
        elif 41 <= volume <= 60:
            fill_color = 0xFD20  # Orange (565 RGB format)
        else:
            fill_color = self.red

        # Calculate the sweep angle for the progress
        sweep_angle = int((volume / max_volume) * 360)

        # Draw the circular progress bar
        for angle in range(0, sweep_angle):
            # Convert angle to radians (rotate by -90 degrees to start from 12 o'clock)
            rad = math.radians(angle - 90)

            # Calculate x and y for the outer and inner circle points
            x_outer = center_x + int(outer_radius * math.cos(rad))
            y_outer = center_y + int(outer_radius * math.sin(rad))
            x_inner = center_x + int(inner_radius * math.cos(rad))
            y_inner = center_y + int(inner_radius * math.sin(rad))

            # Draw a line to fill the arc
            self.line(x_inner, y_inner, x_outer, y_outer, fill_color)

        # Draw the static outer circle border
        self.circle(center_x, center_y, outer_radius, self.white)

        # Draw the volume level in the center
        volume_text = f"{volume}"
        text_x = center_x - (len(volume_text) * 4 * 2)  # Adjust based on text size
        text_y = center_y - 8
        self.draw_scaled_text(volume_text, text_x, text_y, self.white, scale=2)

        # Show the updated display
        self.show()
    
    def _is_point_in_triangle(self, p, p1, p2, p3):
        """
        Helper function to check if a point is inside a triangle using barycentric coordinates.

        Args:
            p (tuple): The point to test (x, y).
            p1, p2, p3 (tuple): Vertices of the triangle.

        Returns:
            bool: True if the point is inside the triangle, False otherwise.
        """
        def sign(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

        b1 = sign(p, p1, p2) < 0
        b2 = sign(p, p2, p3) < 0
        b3 = sign(p, p3, p1) < 0

        return b1 == b2 == b3
    
    def display_play_sign(self, color=None):
        """
        Displays a 'Play' sign (triangle) in the middle of the screen.

        Args:
            color (int): Color of the Play sign (default is white).
        """
        if color is None:
            color = self.white

        # Screen center
        center_x = self.width // 2
        center_y = self.height // 2

        # Define triangle dimensions
        triangle_size = 60  # Size of the triangle
        half_size = triangle_size // 2

        # Calculate triangle vertices
        point1 = (center_x - half_size, center_y - half_size)  # Top left
        point2 = (center_x - half_size, center_y + half_size)  # Bottom left
        point3 = (center_x + half_size, center_y)             # Right point

        # Draw the triangle
        self.line(point1[0], point1[1], point2[0], point2[1], color)  # Left edge
        self.line(point2[0], point2[1], point3[0], point3[1], color)  # Bottom edge
        self.line(point3[0], point3[1], point1[0], point1[1], color)  # Right edge

        # Optionally fill the triangle
        for x in range(point1[0], point3[0]):
            for y in range(point1[1], point2[1]):
                if self._is_point_in_triangle((x, y), point1, point2, point3):
                    self.pixel(x, y, color)

        self.show()
    
    def display_pause_sign(self, color=None):
        """
        Displays a 'Pause' sign (two vertical bars) in the middle of the screen.

        Args:
            color (int): Color of the Pause sign (default is white).
        """
        if color is None:
            color = self.white

        # Screen center
        center_x = self.width // 2
        center_y = self.height // 2

        # Define dimensions of the Pause sign
        bar_width = 25   # Width of each vertical bar
        bar_height = 75  # Height of each vertical bar
        gap = 25         # Gap between the two bars

        # Calculate the coordinates for the two bars
        left_bar_x = center_x - (bar_width + gap // 2)
        left_bar_y = center_y - (bar_height // 2)
        right_bar_x = center_x + (gap // 2)
        right_bar_y = center_y - (bar_height // 2)

        # Draw the left bar
        self.fill_rect(left_bar_x, left_bar_y, bar_width, bar_height, color)

        # Draw the right bar
        self.fill_rect(right_bar_x, right_bar_y, bar_width, bar_height, color)

        self.show()
   
    def fill_triangle(self, p1, p2, p3, color):
        """
        Fills a triangle on the display.

        Args:
            p1, p2, p3 (tuple): Vertices of the triangle (x, y).
            color (int): Color of the triangle.
        """
        # Sort points by y-coordinate
        p1, p2, p3 = sorted([p1, p2, p3], key=lambda p: p[1])

        def edge_interpolate(y, p_start, p_end):
            if p_end[1] == p_start[1]:
                return p_start[0]
            return p_start[0] + (p_end[0] - p_start[0]) * ((y - p_start[1]) / (p_end[1] - p_start[1]))

        for y in range(p1[1], p3[1] + 1):
            if y < p2[1]:
                x1 = edge_interpolate(y, p1, p2)
                x2 = edge_interpolate(y, p1, p3)
            else:
                x1 = edge_interpolate(y, p2, p3)
                x2 = edge_interpolate(y, p1, p3)
            if x1 > x2:
                x1, x2 = x2, x1
            for x in range(int(x1), int(x2) + 1):
                self.pixel(x, y, color)

    def display_skip_to_next_sign(self, color=None):
        """
        Displays a 'Skip to Next' sign (two triangles pointing right and a vertical bar) in the middle of the screen.

        Args:
            color (int): Color of the Skip to Next sign (default is white).
        """
        if color is None:
            color = self.white

        # Screen center
        center_x = self.width // 2
        center_y = self.height // 2

        # Define dimensions
        triangle_size = 30  # Size of each triangle
        bar_width = 15       # Width of the vertical bar
        bar_height = 50     # Height of the vertical bar
        gap = 5             # Gap between the triangles and the bar

        # Calculate triangle vertices (first triangle)
        t1_p1 = (center_x - triangle_size - gap, center_y - triangle_size // 2)  # Top left
        t1_p2 = (center_x - triangle_size - gap, center_y + triangle_size // 2)  # Bottom left
        t1_p3 = (center_x, center_y)                                            # Right

        # Draw the first triangle
        self.line(t1_p1[0], t1_p1[1], t1_p2[0], t1_p2[1], color)  # Left edge
        self.line(t1_p2[0], t1_p2[1], t1_p3[0], t1_p3[1], color)  # Bottom edge
        self.line(t1_p3[0], t1_p3[1], t1_p1[0], t1_p1[1], color)  # Right edge
        self.fill_triangle(t1_p1, t1_p2, t1_p3, color)

        # Calculate triangle vertices (second triangle)
        t2_p1 = (center_x, center_y - triangle_size // 2)  # Top left
        t2_p2 = (center_x, center_y + triangle_size // 2)  # Bottom left
        t2_p3 = (center_x + triangle_size + gap, center_y)  # Right

        # Draw the second triangle
        self.line(t2_p1[0], t2_p1[1], t2_p2[0], t2_p2[1], color)  # Left edge
        self.line(t2_p2[0], t2_p2[1], t2_p3[0], t2_p3[1], color)  # Bottom edge
        self.line(t2_p3[0], t2_p3[1], t2_p1[0], t2_p1[1], color)  # Right edge
        self.fill_triangle(t2_p1, t2_p2, t2_p3, color)

        # Draw the vertical bar
        bar_x = center_x + triangle_size + gap * 2
        bar_y = center_y - bar_height // 2
        self.fill_rect(bar_x, bar_y, bar_width, bar_height, color)

        self.show()

    def display_skip_to_previous_sign(self, color=None):
        """
        Displays a 'Skip to Previous' sign (two triangles pointing left and a vertical bar) in the middle of the screen.

        Args:
            color (int): Color of the Skip to Previous sign (default is white).
        """
        if color is None:
            color = self.white

        # Screen center
        center_x = self.width // 2
        center_y = self.height // 2

        # Define dimensions
        # Define dimensions
        triangle_size = 30  # Size of each triangle
        bar_width = 15       # Width of the vertical bar
        bar_height = 50     # Height of the vertical bar
        gap = 5             # Gap between the triangles and the bar

        # Calculate triangle vertices (first triangle)
        t1_p1 = (center_x + triangle_size + gap, center_y - triangle_size // 2)  # Top right
        t1_p2 = (center_x + triangle_size + gap, center_y + triangle_size // 2)  # Bottom right
        t1_p3 = (center_x, center_y)                                            # Left

        # Draw the first triangle
        self.line(t1_p1[0], t1_p1[1], t1_p2[0], t1_p2[1], color)  # Right edge
        self.line(t1_p2[0], t1_p2[1], t1_p3[0], t1_p3[1], color)  # Bottom edge
        self.line(t1_p3[0], t1_p3[1], t1_p1[0], t1_p1[1], color)  # Left edge
        self.fill_triangle(t1_p1, t1_p2, t1_p3, color)

        # Calculate triangle vertices (second triangle)
        t2_p1 = (center_x, center_y - triangle_size // 2)  # Top right
        t2_p2 = (center_x, center_y + triangle_size // 2)  # Bottom right
        t2_p3 = (center_x - triangle_size - gap, center_y)  # Left

        # Draw the second triangle
        self.line(t2_p1[0], t2_p1[1], t2_p2[0], t2_p2[1], color)  # Right edge
        self.line(t2_p2[0], t2_p2[1], t2_p3[0], t2_p3[1], color)  # Bottom edge
        self.line(t2_p3[0], t2_p3[1], t2_p1[0], t2_p1[1], color)  # Left edge
        self.fill_triangle(t2_p1, t2_p2, t2_p3, color)

        # Draw the vertical bar
        bar_x = center_x - triangle_size - gap * 2 - bar_width
        bar_y = center_y - bar_height // 2
        self.fill_rect(bar_x, bar_y, bar_width, bar_height, color)

        self.show()


if __name__=='__main__':
    pwm = PWM(Pin(BL))
    pwm.freq(1000)
    pwm.duty_u16(32768)#max 65535

    LCD = LCD_1inch3()
    #color BRG
    LCD.fill(LCD.black)
    LCD.show()
    prompt1=f"Connect to {SSID}..."

    LCD.draw_scaled_text(prompt1,10,10,LCD.white,scale=2)
    LCD.show()
    time.sleep(2)
    LCD.clear_screen()
    connect_wifi()
    LCD.show()
    time.sleep(1)

    LCD.draw_scaled_text("Discovering Speakers...",10,10,LCD.white,scale=2)
    LCD.show()
    time.sleep(2)
    LCD.clear_screen()

    devices=discover_sonos_devices()
    sonos_ip=devices[1]

    LCD.draw_scaled_text(f"Hooked to Speaker {sonos_ip}",10,10,LCD.white,scale=2)
    LCD.show()
    time.sleep(2)
    LCD.clear_screen()
    
    keyA = Pin(15,Pin.IN,Pin.PULL_UP)
    keyB = Pin(17,Pin.IN,Pin.PULL_UP)
    keyX = Pin(19 ,Pin.IN,Pin.PULL_UP)
    keyY= Pin(21 ,Pin.IN,Pin.PULL_UP)
    
    up = Pin(2,Pin.IN,Pin.PULL_UP)
    dowm = Pin(18,Pin.IN,Pin.PULL_UP)
    left = Pin(16,Pin.IN,Pin.PULL_UP)
    right = Pin(20,Pin.IN,Pin.PULL_UP)
    ctrl = Pin(3,Pin.IN,Pin.PULL_UP)
    
    while(1):
        if keyA.value() == 0:
            pass
            
        if(keyB.value() == 0):
            pass
            
        if(keyX.value() == 0):
            pass
  
            
        if(keyY.value() == 0):
            pass

            
        if(up.value() == 0):
            set_volume_up(sonos_ip,get_current_volume(sonos_ip))
            LCD.display_volume_level(get_current_volume(sonos_ip))
            time.sleep(0.1)
        else:
            LCD.fill(0x0000)

        if(dowm.value() == 0):
            set_volume_down(sonos_ip,get_current_volume(sonos_ip))
            LCD.display_volume_level(get_current_volume(sonos_ip))
            time.sleep(0.1)

            
        if(left.value() == 0):
            skip_to_prev_song(sonos_ip)
            LCD.display_skip_to_previous_sign()
            get_album_image_url(sonos_ip)
            time.sleep(0.1)
        
        if(right.value() == 0):
            skip_to_next_song(sonos_ip)
            LCD.display_skip_to_next_sign()
            LCD.draw_scaled_text(get_album_image_url (sonos_ip),10,10,LCD.white,scale=2)
            time.sleep(1)
        
        if(ctrl.value() == 0):
            play_pause (sonos_ip)
            if ((get_transport_state(sonos_ip)) == "PLAYING"):
                LCD.display_play_sign()
            else:
                LCD.display_pause_sign()
            time.sleep(1)

                       
        LCD.show()
    time.sleep(1)




