# Shocking VRChat

> This document is translated by AI.

A small tool that uses WebSocket protocol to link Coyote DG-LAB 3.0 with VRChat avatars by receiving OSC messages. This allows the Coyote device to deliver electric shocks when the avatar is touched by others or themselves in the game.

> [!CAUTION]
> You must read and agree to the [Safety Precautions](doc/dglab/SafetyPrecautions.md) before using this tool!

Our VRChat Group: [ShockingVRC https://vrc.group/SHOCK.2911](https://vrc.group/SHOCK.2911)

## Usage

1. Go to [Project Release](https://github.com/VRChatNext/Shocking-VRChat/releases) to download the latest version of the Shocking-VRChat tool.
2. Run the exe program for the first time, which will generate a settings file in the current directory and then exit.
3. Fill in `avatar_params` and the working mode (shock/distance) in the configuration file `settings-v*.*.yaml`.
4. (Optional) Modify the advanced configuration file `settings-advanced-v*.*.yaml` as needed. Refer to the advanced configuration file reference for parameter meanings.
5. Run the program again and check if the Windows Firewall security warning pops up. If it does, choose to allow it to accept the connection from the Coyote APP.
6. Launch the DG-LAB 3.0 APP and use the Socket control function to scan the QR code from the pop-up window.
7. Enjoy VRChat!

## Working Mode Explanation

### distance Mode

- Controls waveform intensity based on the distance to the center of the trigger area.
- The closer to the center, the stronger the intensity.
- In distance mode, the meaning of `trigger_range` is:
    - When received OSC data is greater than `bottom`, waveform intensity starts to change linearly, with the upper limit as `top`.
    - When the data reaches or exceeds the `top` parameter, it outputs at maximum intensity.
    - It is recommended to set `bottom` to 0 or a small number.
    - It is recommended to set `top` to 1.0 for the maximum dynamic range.

### shock Mode

- Triggers a fixed duration electric shock (default: 2 seconds).
- If continuously touched, the shock continues for a fixed duration after the touch ends.
- In shock mode, the meaning of `trigger_range` is:
    - When received OSC data is greater than `bottom`, it triggers the shock.
    - The `top` parameter is ignored in shock mode.

## Basic Configuration File Reference

The configuration file format is `yaml`. The current configuration file version: `v0.2`.

```yaml
dglab3:
  channel_a:
    avatar_params:
    # Fill in OSC listening parameters here. You can use wildcards * to match any string. Be sure to maintain proper indentation and prefix with "- ".
    # Refer to https://python-osc.readthedocs.io/en/latest/dispatcher.html#mapping
    - /avatar/parameters/pcs/contact/enterPass
    - /avatar/parameters/Shock/wildcard/*
    mode: distance # Working mode, here is distance mode
    strength_limit: 100 # Strength limit, the program will take the maximum of this strength and the host's set strength
  channel_b:
    avatar_params:
    - /avatar/parameters/lms-penis-proximityA*
    - /avatar/parameters/ShockB2/some/param
    mode: shock # Working mode, here is shock mode
    strength_limit: 100
version: v0.2
```

## Model Parameter Configuration

- Internal parameters processed by the program range between 0 and 1 (float).
- Supported input parameter types are float, int, and bool:
    - float, int: Values less than 0 are considered 0, and values greater than 1 are considered 1.
    - bool: True is considered 1, False is considered 0.
- Other parameter types will cause an error.

## Common Parameters

> Please help to supplement descriptions and explanations for this section.

- float
  - /avatar/parameters/pcs/contact/enterPass
    - Most commonly used, located at the pcs trigger entrance, can automatically switch following the triggered position
  - /avatar/parameters/pcs/contact/proximityA
  - /avatar/parameters/pcs/contact/proximityB
  - /avatar/parameters/pcs/contact/slide
  - /avatar/parameters/pcs/smash-intensity
  - /avatar/parameters/pcs/sps/pussy
    - If you need to trigger from a specified position only, try parameters under pcs/sps, which won't follow auto mode position changes
  - /avatar/parameters/pcs/sps/ass
  - /avatar/parameters/pcs/sps/boobs
  - /avatar/parameters/pcs/sps/mouth
  - /avatar/parameters/pcs/sps/penis*
  - /avatar/parameters/lms-penis-proximityA*
    - Parameters usable for triggering via LMS 1.2
  - /avatar/parameters/lms/contact/proximity
    - Parameters usable for triggering via LMS 1.3
- bool
  - /avatar/parameters/pcs/smash-intense
  - /avatar/parameters/pcs/contact/in
  - /avatar/parameters/pcs/contact/out
  - /avatar/parameters/pcs/contact/hit
  - /avatar/parameters/lms-stroke-in
  - /avatar/parameters/lms-stroke-out*
  - /avatar/parameters/lms-stroke-smash

## Advanced Configuration File Reference

```yaml
SERVER_IP: null # When null, the program will attempt to automatically obtain the local IP. If incorrect, change null to the correct IP address (the one that the phone can access, usually the wired network or WiFi)
dglab3:
  channel_a: # Channel A configuration
    mode_config:   # Working mode configuration
      distance:
      # Parameters under this item only apply to distance mode
        freq_ms: 10 
        # Frequency of waveform generation (interval in milliseconds), recommended 10 
        # For details, refer to the waveform section of the DG-LAB-OPENSOURCE Bluetooth protocol V3
      shock:
      # Parameters under this item only apply to shock mode
        duration: 2
        # Duration of the shock after triggering
        wave: '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]'
        # Shock waveform
      trigger_range:
      # Trigger threshold settings, effective for all modes, range 0 ~ 1
        bottom: 0.0 # Lower bound of the OSC reporting parameter (values below are considered 0%)
        top: 0.8    # Upper bound of the OSC reporting parameter (values above are considered 100%)
  channel_b: # Channel B configuration, parameter settings are the same as Channel A
    mode_config:
      distance:
        freq_ms: 10
      shock:
        duration: 2
        wave: '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]'
      trigger_range:
        bottom: 0.1
        top: 0.8
general: # General configuration
  auto_open_qr_web_page: true # Automatically open the scan code web page when the program starts
  local_ip_detect:  # Server address for detecting local IP
    host: 223.5.5.5 # Default is AliDNS. If used outside mainland China, modify accordingly
    port: 80
log_level: INFO # Log level, can be changed to DEBUG for troubleshooting
osc: # OSC service configuration
  listen_host: 127.0.0.1 # If VRChat runs on another host, change to 0.0.0.0 and configure VRChat with the correct OSC startup command line parameters.
  listen_port: 9001
version: v0.2 # Configuration file version
web_server: # Web server configuration
  listen_host: 127.0.0.1 # If you need to open the web page for scanning from another host, change to 0.0.0.0
  listen_port: 8800
ws: # WebSocket service configuration
  listen_host: 0.0.0.0
  listen_port: 28846
  master_uuid: 6da2fd3b-a6e5-4af4-afc1-96bfd2e9e95c # Automatically generated randomly on first startup
```

## FAQ

### Is there an escape route?

- Yes, you can press any shoulder button on the Coyote. This will set the strength of channels A and B to 0.
- When the program detects that the channel strength is manually set to 0, it will no longer automatically follow the strength limit.
- To restore, manually click the "+" button on the phone to increase the channel strength by 1, thereby resuming automatic following.

### How should I set the strength limit?

- It is recommended to adjust through the controlled settings in the Coyote APP. The program will follow these settings.
- The `strength_limit` in the basic configuration file `settings-v*.*.yaml` also limits the maximum strength. If it exceeds the default value of 100, you need to adjust this parameter.
- To ensure the strength follows automatically, make sure that the initial strength limit value (minimum value) of both channels in the Coyote APP's controlled settings menu is greater than or equal to 1.

### How can I use one parameter to trigger two channels simultaneously?

- Copy the parameter you want to use, such as `/avatar/parameters/pcs/contact/enterPass`, into the `avatar_params` list of both `channel_a` and `channel_b` in the basic configuration file `settings-v*.*.yaml`. Pay attention to the indentation and the `-` at the beginning of the line.

### The waveform is output in the console, but there's no strength or the strength significantly decreases.

- Try pressing a button to set the Coyote's strength to 0, then manually click the screen to increase it by 1 to resume normal mode.

### The program doesn't seem to receive OSC data.

1. **If you have face tracking**, check the launch command line parameters of VRChat in Steam to see if there is a configuration similar to `--osc=9000:127.0.0.1:9001`. If so, modify the `osc` `listen_port` value in the advanced configuration file to the value after the last colon, such as 9001.
2. In the Action Menu, select Options > OSC > Reset Config to reset the OSC configuration.
3. If it was working normally before but suddenly stopped, restarting the computer might solve the problem, which seems to be a VRChat bug.

### Why is the strength always at the maximum available value?

- After running the program, it will automatically follow the upper limit set in the Coyote APP and set the maximum strength by taking the minimum of this value and the `strength_limit` in the basic configuration file.
- The program uses waveform signals to control strength. Even if you see the strength reaching the upper limit, the actual triggered strength is determined by the distance between the trigger entity (e.g., another player's hand) and the center of the trigger area (e.g., enterPass), increasing linearly.
- To modify the judgment thresholds, use the `trigger_range` configuration.

### The APP cannot connect/connection times out when scanning the QR code.

1. Make sure the phone and computer are on the same network, for example, the phone cannot use mobile data.
2. Check the IP address displayed on the QR code webpage, such as ws://192.168.1.2:28846/. Is this IP address correct for your network card?
3. If the IP is incorrect, fill in the correct IP address in the advanced configuration file under `SERVER_IP:` and restart the program to try again.
4. Check if the Windows firewall allows this program to access the network (accept incoming connections).

### How to inherit configuration files after program updates?

- The program version and configuration file version are separate. If only the program version is updated, the configuration file does not need to be modified and can be used as is.
- If the configuration file version is updated, the original configuration will not be overwritten. Observe the changes in the new configuration file and fill in the necessary parameters into the new configuration file.

### OSC can receive other parameters but not the model's parameters.

- If your model has just been modified, it's possible that VRChat's OSC configuration file hasn't been updated. Try resetting the OSC configuration in the Action Menu by selecting Options > OSC > Reset Config.

## Credits

Thanks to [DG-LAB-OPENSOURCE](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE). Praise the open-source spirit of DG-LAB!

-----

## Safety Precautions:

**To ensure your healthy enjoyment of the product, please make sure to read and understand all the contents of this safety notice before use.**  
**Improper use of this product may cause harm to you or others, and you will be responsible for any resulting liability.**

Thank you for choosing the DG-LAB series of products. User safety is always our top priority.  
This product is a sex toy, make sure to use in a **safe, sober, voluntary** basis. And please place this product in a location that is inaccessible to minors.

This safety notice takes approximately **2 minutes** to read.

### **This product is strictly forbidden to be used by the following people:**

1. **People with pacemakers or electronic/metal implants in their bodies** (which may affect the normal function of pacemakers or implants).
2. **Patients with epilepsy, asthma, heart disease, thrombosis, and other cardiovascular and cerebrovascular diseases** (sensory stimulation may induce or exacerbate symptoms).
3. **Patients with sensitive skin, eczema, and other skin diseases** (may aggravate skin disease symptoms).
4. **Patients with bleeding tendency diseases** (electrical stimulation may cause local capillary dilation and potential bleeding).
5. Minors, pregnant women, people with abnormal perception and no expressive ability.
6. People with limb movement disorders and other people **who cannot operate the product in a timely manner** (may not be able to stop output when feeling uncomfortable).
7. Other people who are undergoing treatment or are physically uncomfortable.

### **The following areas are strictly prohibited from using this product:**

1. The electrodes must not be placed on the chest. **It is absolutely forbidden to place the two electrodes in front and back, left and right of the heart projection area** or any position where the current may pass through the heart.
2. The electrodes must not be placed **near the head, face, eyes, mouth, and neck.**
3. The electrodes must not be placed on **damaged or swollen skin, joint sprains and bruises, muscle strains, inflammation/infection lesions, or near wounds that have not completely healed.**

### **Other precautions:**

1. **It is strictly forbidden to use the same part for more than 30 minutes continuously. **Long-term use may cause local redness, swelling, decreased sensation, and other injuries.
2. Do not move the electrode in the output state. **When moving the electrode or replacing the electrode, you must stop the output first** to avoid changes in contact area causing stinging or burns.
3. It is strictly prohibited to use this product in dangerous situations such as driving or operating the machine to **avoid losing control due to pulse effects.**
4. It is strictly forbidden to insert electrode wires into places other than the mainframe wire plug hole (such as power sockets).
5. It is strictly forbidden to use in places with flammable and explosive substances.
6. **Do not use multiple devices simultaneously.**
7. Do not disassemble or repair the product host without authorization, which may cause malfunctions or unexpected outputs.
8. Do not use in humid environments such as bathrooms.
9. During use, **avoid allowing the two electrodes to come into contact and create a short circuit. **This may result in reduced effectiveness, discomfort or burns at the contact site, or damage to the device.
10. During electrode use, it is essential for them to be **in close and full contact with the skin. **Inadequate contact may result in stinging or burns. If the contact area between the electrode and the skin is too large, it may lead to weak electrical sensation.
11. The product contains lithium batteries. It is prohibited to disassemble, reassemble, squeeze or put them into fire. **If the product malfunctions or overheats abnormally, **please do not continue to use it.

### **Important usage tips:**

1. Due to variations in the tolerance of different body parts to electrical currents and the potential for some materials in the electrodes to cause allergic reactions in a small number of users, **it is recommended to conduct a 10-minute trial when using this product on a new area for the first time or with a new set of electrodes. **After the trial, take a break and ensure there are no adverse reactions at the application site before continuing use.
2. Due to the physiological characteristics of the human body, the sensitivity to sustained pulse stimulation will gradually decrease during use. Therefore, it may be necessary to gradually increase the intensity during use to maintain a relatively stable physical sensation stimulation intensity.  
This may result in **real stimulation intensity gradually exceeding the acceptable range but not being felt after using the same part of the body for a long time, **resulting in damage.  
Although the maximum output of this product strictly complies with safety standards (r.m.s < 50ma, 500Ω), long-term use may still cause harm to your body.Therefore, **strictly adhere to the duration limits during use. **After continuous use in the same area for **30 minutes,** take a break to allow sensitivity to return to normal levels.
3. Continuous and uninterrupted high-frequency stimulation may cause rapid adaptation at the application site. It is recommended to use waveforms with **changing frequencies and intermittent rests **for a better user experience. Each segment of waveform stimulation can be set between 1 to 10 seconds, with a rest period of 1 to 10 seconds being advisable.
