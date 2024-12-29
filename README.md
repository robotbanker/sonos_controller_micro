# Sonos Controller Micro

Sonos Controller Micro is a lightweight and efficient controller for Sonos speakers. This project aims to provide a minimalistic yet powerful interface to manage and control your Sonos devices.

## Features

- Discover and list available Sonos speakers on your network
- Control playback (play, pause, stop, next, previous)
- Adjust volume and mute/unmute
- Group and ungroup speakers
- Manage playlists and queues
- Cross-platform compatibility

## Hardware Requirements

- **Raspberry Pi Pico W**: The microcontroller used to run the application.
- **Waveshare Display HAT**: The display interface for the controller. The display is initialized in the code as `Class LCD1.3`.

## Installation

To install and run the Sonos Controller Micro, follow these steps:

1. **Clone the repository:**

    ```bash
    git clone https://github.com/robotbanker/sonos_controller_micro.git
    cd sonos_controller_micro
    ```

2. **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3. **Upload the code to Raspberry Pi Pico W:**

    Use your preferred method to upload the code to the Raspberry Pi Pico W. You can use tools like Thonny IDE or rshell.

4. **Connect the Waveshare Display HAT:**

    Ensure that the Waveshare Display HAT is properly connected to the Raspberry Pi Pico W.

5. **Run the application:**

    ```bash
    python app.py
    ```

## Usage

Once the application is running, you can use the provided interface to manage your Sonos speakers. The interface offers various controls and settings to customize your listening experience.

## Configuration

You can configure the application by modifying the `config.json` file. This file includes settings such as network discovery options, default volume levels, and other preferences.

## Framework

The code for this project is based on the official SONOS XML Framework: [http://schemas.xmlsoap.org/soap/envelope/](http://schemas.xmlsoap.org/soap/envelope/). This framework allows for efficient communication and control of Sonos devices using standard SOAP (Simple Object Access Protocol) messages.

## Contributing

We welcome contributions to improve the Sonos Controller Micro. To contribute, please follow these steps:

1. Fork the repository
2. Create a new branch (`git checkout -b feature-branch`)
3. Make your changes and commit them (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature-branch`)
5. Create a new Pull Request

## License

This project is licensed under the MIT License. See the `LICENSE` file for more details.

## Contact

For any questions or feedback, please open an issue on the [GitHub repository](https://github.com/robotbanker/sonos_controller_micro).
