init python:
    import json
    import requests
    import os
    import urllib.request
    import urllib.parse
    import ssl
    import base64
    import re

    class AutoScriptGPT:
        # Initialization of the AutoScriptGPT class
        def __init__(
            self, 
            player, 
            partner,
            images_dir,
            placeholder,
            GEMINI_API_KEY,
            ssl_context
        )->None:
            self.player = player    
            self.partner = partner
            self.is_running = True
            self.conversation_history = []
            self.load_config()
            self.load_game()
            self.parser = AutoScriptParser(self.player, self.partner)
            self.initial_prompt = self.generate_initial_prompt()
            self.images_dir = images_dir
            self.placeholder = placeholder
            self.GEMINI_API_KEY = GEMINI_API_KEY
            self.ssl_context = ssl_context
            
            # Dictionary to store avatar file paths
            self.avatar_files = {}
            
            # Define avatar prompts for each character
            self.avatar_prompts = {
                "player": f"A portrait of {self.player.name}, a brave adventurer. Style: medieval fantasy, detailed illustration.",
                "partner": f"A portrait of {self.partner.name}. Style: medieval fantasy, detailed illustration."
            }
            
            # Generate and store avatar images
            self.generate_avatars()

        # Load game configuration from the provided files
        def load_config(self):
            with open(ENDING_CONFIG_FILE, 'r') as f:
                self.ending_config = json.load(f)
            with open(STORY_INSTRUCTIONS_FILE, "r") as f:
                self.story_instructions = f.read().format(self=self)
                
        # Generate avatar images for characters
        def generate_avatars(self):
            # Generate player avatar
            player_avatar_path = self.fetch_image(self.avatar_prompts["player"])
            self.avatar_files["Player"] = self.get_image(player_avatar_path)
            
            # Generate partner avatar
            partner_avatar_path = self.fetch_image(self.avatar_prompts["partner"])
            self.avatar_files["Partner"] = self.get_image(partner_avatar_path)
            
            # Show the player avatar screen
            renpy.show_screen("player_avatar", avatar_files=self.avatar_files)
                
        # Generate the initial prompt for the game based on the loaded configurations
        def generate_initial_prompt(self):
            attribute_details = "; ".join([
                f"Modify {attribute_name} by: 'increase/decrease {attribute_name} [value]' (Range: {attribute_data['range'][0]}-{attribute_data['range'][1]})"
                for attribute_name, attribute_data in self.partner.attributes.items()
            ])
            return f"""
Event-Based Visual Novel Guide:

Story: {self.story_instructions}
Attributes: {attribute_details} (e.g. increase/decrease health by 10)

Rules:

1. Keep the story moving forward; avoid repetition.
2. Present up to 3 menu choices with hidden outcomes.
3. Do not use '[ ]' except for emotion and setting tags as specified.
4. Frequent attribute modifications are encouraged.
5. In *Dialog*, include the partner's emotion in brackets, e.g., {self.partner.name}: [Happy] Hello!
6. In *Narration*, start with a setting keyword in brackets, e.g., [Setting: Forest] The trees swayed gently.

Follow this STRICT format:

*Modify Attributes*
[Insert changes here or state 'None' if no changes]

*Dialog*
{self.partner.name}: [Emotion] [Dialog]
{self.player.name}: [Reply]

*Narration*
[Setting: Keyword] [Concisely describe settings, actions, or events without using ':']

*Image*
[Describe the scene or character for image generation]

*Menu*
1. [option 1]
2. [option 2]
3. [option 3]

Avoid additional space between lines.
"""
        # Main method to run the game loop
        def run(self):
            # The starting point is either the initial_prompt or the last item in conversation history.
            starting_point = self.initial_prompt if not self.conversation_history else self.conversation_history[-1]
            # Initialize with the starting point
            res = self.getResponse(starting_point)
            self.conversation_history.append(res)
            while self.is_running:
                narrator("Click the next button and wait for a minute...")
                
                # Extract image prompt and generate image if available FIRST
                image_prompt = self.extract_image_prompt(res)
                print("IMAGE PROMPT\n",image_prompt)
                if image_prompt:
                    print(f"Extracted image prompt: {image_prompt}")
                    image_path = self.fetch_image(image_prompt)
                    print(f"Generated image at: {image_path}")
                    
                    # Display the image directly using show_scene_image BEFORE parsing dialog
                    print(f"Displaying image directly: {image_path}")
                    show_scene_image(image_path)
                
                # Make sure player avatar is shown
                renpy.show_screen("player_avatar", avatar_files=self.avatar_files)
                
                # Parse the dialog and get user input AFTER showing the image
                op = self.parser.parse_auto_dialog(res, self.avatar_files)
                
                # Get the next response
                res = self.getResponse(op)
                self.conversation_history.append(res)
                
                # Check conditions only if still running to optimize performance
                if self.is_running and len(self.conversation_history) >= SUMMARIZE_INTERVAL:
                    self.summarize_and_append()
                self.check_game_ending()
            
        # Extract image prompt from the response
        def extract_image_prompt(self, response):
            """Extract image prompt from the response."""
            # Look for the *Image* section
            image_section_match = re.search(r'\*Image\*\s*\n(.*?)(?:\n\n|\Z)', response, re.DOTALL)
            if image_section_match:
                # Return the content of the image section
                return image_section_match.group(1).strip()
            
            # If no *Image* section, try to extract a scene description from narration
            narration_match = re.search(r'\*Narration\*\s*\n\[Setting: (.*?)\](.*?)(?:\n\n|\Z)', response, re.DOTALL)
            if narration_match:
                setting = narration_match.group(1).strip()
                description = narration_match.group(2).strip()
                return f"{setting} scene with {description}"
            
            return None
            
        # Check if game should end based on the ending configurations
        def check_game_ending(self):
            for ending in self.ending_config:
                attribute_value = self.partner.get_attribute_value(ending['attribute'])
                if attribute_value is not None and eval(f"{attribute_value} {ending['condition']} {ending['value']}"):
                    custom_ending = self.generate_custom_ending()
                    print(custom_ending)
                    self.parser.parse_auto_dialog(custom_ending)
                    narrator(ending['message'])
                    destroy_saved_data()
                    self.is_running = False
                    return

        # Load previously saved game state
        def load_game(self):
            if os.path.exists(SAVE_FILE_PARTNER) and (os.stat(SAVE_FILE_CONVERS).st_size != 0):
                with open(SAVE_FILE_PARTNER, 'r') as file:
                    data = json.load(file)
                    self.partner = load_from_json(data, self.partner)
                if os.path.exists(SAVE_FILE_CONVERS) and (os.stat(SAVE_FILE_CONVERS).st_size != 0):
                    with open(SAVE_FILE_CONVERS, 'r') as file:
                        self.conversation_history = json.load(file)
                narrator("Game data loaded.")
            else:
                narrator("No saved game data found.")
        
        # This method helps in generating a summary for the game progression
        def summarize_and_append(self):
            summarized_storyline = self.summarize_storyline('\n'.join(str(x) for x in self.conversation_history[1:]))
            print("Summarized Storyline: ", summarized_storyline)
            self.conversation_history = [self.initial_prompt, summarized_storyline]
    
        # Summarize the storyline for the player
        def summarize_storyline(self, pre_summary_context) -> str:
            prompt =  f"""Recap of the journey:
        
            {pre_summary_context}
        
            Based on the above, provide a short summary:
            1. Highlight key decisions and events.
            2. Detail characters' emotional journeys.
            3. Include vital dialogues and interactions.
        
            After summarizing, continue the story from the last decision.
        
            """
            return self.getResponse(prompt)

        # Generate a custom ending for the game based on character attributes
        def generate_custom_ending(self):
            partner_attributes = [attr for attr in dir(self.partner) if not callable(getattr(self.partner, attr)) and not attr.startswith('__')]
            status_context = "\n".join([f"Partner {attr.capitalize()}: {getattr(self.partner, attr)}" for attr in partner_attributes])
            conversation_context = "\n".join(self.conversation_history[-5:])  # Last 5 conversations for context
            prompt = f"""Based on the journey and current status:
            {status_context}

            Recent events:
            {conversation_context}
            
            Craft a suitable ending for the story, considering the choices made, the emotions felt, the events that have unfolded, and the current status.
            
            """
            ending = self.getResponse(prompt)
            return ending
        
        # Communicate with the GPT model to get the desired response
        def getResponse(self, prompt) -> str:
            import os
            OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
            
            if not OPENAI_API_KEY:
                print("OPENAI_API_KEY environment variable not set")
                narrator("API key not found. Please set the OPENAI_API_KEY environment variable.")
                return ""
                
            self.conversation_history.append(prompt)
            
            # Prepare request data
            headers = {
                'Authorization': f'Bearer {OPENAI_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            # Create context from partner attributes
            partner_attrs = [attr for attr in dir(self.partner) 
                            if not callable(getattr(self.partner, attr)) 
                            and not attr.startswith("__")]
            context = '\n'.join([f"Partner {attr.capitalize()}: {getattr(self.partner, attr)}" 
                                for attr in partner_attrs])
            
            # Prepare request payload
            data = {
                "model": MODEL_NAME,
                'messages': [{'role': 'system', 'content': context}]
            }
            data['messages'].extend([{'role': 'user', 'content': message} for message in self.conversation_history])
            
            # Make API request
            response = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data)
            
            # Handle response
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                print(f"API error: {response.status_code} - {response.text}")
                self.conversation_history.pop()  # Remove the failed prompt
                narrator("An error occurred while communicating with the GPT model. Please try again.")
                return ""

        def fetch_image(self, prompt:str)->str:
            """
            Generate an image using the Gemini API and save it to a file.

            Parameters:
            - prompt (str): The text prompt for generating the image.
            
            Returns:
            - str: The path to the generated image file
            """
            if not self.GEMINI_API_KEY:
                print("GEMINI_API_KEY not available")
                return self.placeholder
                
            # Create a safe filename from the prompt
            safe_filename = '_'.join(prompt.split(' ')[:6])
            safe_filename = ''.join(c if c.isalnum() or c == '_' else '_' for c in safe_filename)
            
            # Ensure cache directory exists
            cache_dir = os.path.join(renpy.config.gamedir, "cache", "images")
            os.makedirs(cache_dir, exist_ok=True)
            
            # Create the full output path in the cache directory
            output_file = os.path.join(cache_dir, f"image_{safe_filename}.png")
            
            # If the file already exists, return its path
            if os.path.exists(output_file):
                print(f"Image already exists at: {output_file}")
                return output_file
                
            print(f"Generating image for prompt: {prompt}")
            
            # Prepare API request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp-image-generation:generateContent?key={self.GEMINI_API_KEY}"
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "responseModalities": ["Text", "Image"]
                }
            }
            
            # Make the request
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url, 
                data=data, 
                headers={'Content-Type': 'application/json'}, 
                method='POST'
            )
            
            # Process the response
            try:
                with urllib.request.urlopen(req, context=self.ssl_context) as response:
                    if response.status != 200:
                        print(f"Error: {response.status}")
                        return self.placeholder
                        
                    response_data = response.read().decode('utf-8')
                    response_json = json.loads(response_data)
                    image_data = response_json['candidates'][0]['content']['parts'][0]['inlineData']['data']
                    
                    # Save the image
                    with open(output_file, 'wb') as f:
                        f.write(base64.b64decode(image_data))
                    
                    print(f"Image saved as '{output_file}'")
                    return output_file
            except Exception as e:
                print(f"Error generating image: {e}")
                return self.placeholder

        def get_image(self, path):
            """Convert image path to a format Ren'Py can use"""
            import renpy
            
            # Handle absolute paths
            if os.path.isabs(path):
                if os.path.exists(path) and path.startswith(renpy.config.gamedir):
                    # Convert to relative path for Ren'Py
                    return os.path.relpath(path, renpy.config.gamedir)
                return self.placeholder
                
            # Handle relative paths
            if renpy.loadable(path):
                return path
            return self.placeholder
                
# # RenPy persistent data setup
# init -2 python:
#     import renpy.store
#     renpy.store.persistent = {}
