init python:
    import re
    import json
    
    class AutoScriptParser:
        # Constants to identify different script parts
        DIALOG_PREFIX = "*Dialog*"
        NARRATION_PREFIX = "*Narration*"
        MENU_PREFIX = "*Menu*"
        MODIFY_ATTRIBUTES_PREFIX = "*Modify Attributes*"
        
        # Regular expression pattern to split text into sentences
        SPLITTER = re.compile(r"""
            (?:
                (?<=[.!?])                  # After any end of sentence punctuation
                (?!Mr\.|Mrs\.|mr\.|mrs\.)   # Negative lookahead to ensure not followed by 'mr.' or 'mrs.' 
                |(?<=\.[\"'])               # After a quote at the end of a sentence
                |\.\s                       # A period followed by whitespace
            )
            \s                              # Any whitespace following (space and/or newline)
            (?=[A-Z])                       # Lookahead for an uppercase letter (start of next sentence)
        """, re.VERBOSE)
        
        STATIC_REPLACEMENTS = {
        '[': '(',
        ']': ')',
        '\"': '',
        }
        
        def __init__(self, player, partner):
            self.player = player
            self.partner = partner
            self.current_speaker = None
        
        def sanitize_text(self, text):
            """Sanitize text for consistent parsing."""
            replacements = self.STATIC_REPLACEMENTS.copy()
            # Create a mapping of patterns to their replacements
            mapping = {
                '(player': self.player.name,
                '(Player': self.player.name,
                '(partner': self.partner.name,
                '(Partner': self.partner.name
            }
            # Construct the replacement patterns and their corresponding values
            for base_name, name in mapping.items():
                replacements.update({
                    base_name + suffix: name
                    for suffix in ['_name)', '_Name)', ' Name)', ' name)']
                })
            # Perform the replacements
            for key, value in replacements.items():
                text = text.replace(key, value)        
            return text

        def _process_text(self, line, char_name=None, avatar_files=None):
            """Helper function to process dialog or narration lines."""
            sentences = split_into_sentences(line)
            
            # Show appropriate character avatar based on who is speaking
            if char_name:
                # Handle character-specific avatar display
                if char_name == self.partner.name and avatar_files and "Partner" in avatar_files:
                    # Show partner avatar
                    renpy.show_screen("partner_avatar", avatar_files=avatar_files)
                    self.current_speaker = char_name
                elif char_name != self.player.name and char_name != "Player":
                    # For any other NPC, we could show a generic NPC avatar if available
                    pass
                
                # Process the text
                for sentence in sentences:
                    if ('modify' in char_name.lower()) >= 0:
                        continue
                    renpy.say(who=char_name, what=sentence)
            else:
                # For narration
                for sentence in sentences:
                    narrator(sentence)

        def parse_auto_dialog(self, response, avatar_files=None):
            """Main parsing function to process the auto dialog script."""
            # Dictionary mapping prefixes to their corresponding parser functions
            parsers = {
                self.DIALOG_PREFIX: self.parse_dialog,
                self.NARRATION_PREFIX: self.parse_narration,
                self.MENU_PREFIX: self.parse_menu,
                self.MODIFY_ATTRIBUTES_PREFIX: self.parse_attribute_modifications,
                "*Image*": self.parse_image
            }
            if not response:
                return "Continue the story from where it left off."
            # Sanitize the response to ensure correct parsing
            sanitized_response = self.sanitize_text(response)
            # Split response into distinct parts and apply the respective parser based on the header
            parts = sanitized_response.split("\n\n")
            for part in parts:
                lines = part.split("\n")
                if lines[0] in parsers:
                    result = parsers[lines[0]](lines, avatar_files)  # Calling the appropriate parser function with avatar_files
                    if result:  # If the parser returns a result, we return it
                        return result
                else:
                    for line in lines:
                        if line.find(':') == -1 and line != '(Narration)' and line != '*Narration Continues*' and line != 'None':
                            if line != '*dialog*' and line != '*narration*':
                                self._process_text(line, None, avatar_files)
                        else:
                            char_name, _, char_dialog = line.partition(':')
                            self._process_text(char_dialog, char_name, avatar_files)
                # If no specific parser was triggered, return the default string
            return "Continue the story from where it left off."

        def parse_image(self, lines, avatar_files=None):
            """Parse image lines but don't display the image (it's already displayed in auto_script.rpy)."""
            
            # We don't need to display the image here since it's already displayed in auto_script.rpy
            # This function is kept for compatibility and logging purposes
            
            # First, check if there's an image path in the format (Image: path) in any of the lines
            for line in lines:
                if '(Image: ' in line:
                    image_path = line.split('(Image: ')[1].split(')')[0]                    
                    # Just log if the image exists but don't display it
                    if os.path.exists(image_path):
                        print(f"Image exists at: {image_path}")
                    else:
                        print(f"Image does not exist at: {image_path}")
                        # Try to find the image in the cache directory
                        filename = os.path.basename(image_path)
                        cache_path = os.path.join(renpy.config.gamedir, "cache", "images", filename)
                        if os.path.exists(cache_path):
                            print(f"Found image in cache: {cache_path}")
                        else:
                            print(f"Image not found in cache either: {cache_path}")
            
            # If we get here, no image path was found in the format (Image: path)
            # Let's check if there's an image path in the response itself
            if len(lines) > 1:
                # The second line (index 1) should be the image path or prompt
                image_prompt = lines[1]
                print(f"Image prompt found: {image_prompt}")
                
                # Create a safe filename from the prompt for logging
                safe_filename = '_'.join(image_prompt.split(' ')[:6])
                safe_filename = ''.join(c if c.isalnum() or c == '_' else '_' for c in safe_filename)
                cache_path = os.path.join(renpy.config.gamedir, "cache", "images", f"image_{safe_filename}.png")
                
                if os.path.exists(cache_path):
                    print(f"Found matching image in cache: {cache_path}")
            
            # Just return None to continue the dialog flow
            return None

        def parse_dialog(self, lines, avatar_files=None):
            """Parse dialog lines."""
            for line in lines[1:]:
                char_name, _, char_dialog = line.partition(':')
                char_name = char_name or self.player.name
                self._process_text(char_dialog, char_name, avatar_files)

        def parse_narration(self, lines, avatar_files=None):
            """Parse narration lines."""
            for line in lines[1:]:
                self._process_text(line, None, avatar_files)

        def parse_menu(self, lines, avatar_files=None):
            """Parse menu options and return player's choice."""
            player_options = [(line.split('. ')[1], line.split('. ')[1]) for line in lines[1:] if '. ' in line]
            if player_options:
                player_options.append(("Input your own text...", "USER_TEXT_INPUT"))
                choice = renpy.display_menu(player_options)
                if choice == "USER_TEXT_INPUT":
                    user_input = renpy.input("What would you like to say?")
                    return user_input.strip() if user_input else None
                return choice

        def parse_attribute_modifications(self, lines, avatar_files=None):
            """Parse attribute modifications like 'increase' or 'decrease'."""
            for line in lines[1:]:
                line = line.lstrip('-')
                mod_instruction_parts = line.split(' ')
                if len(mod_instruction_parts) > 2:
                    if (('increase' in mod_instruction_parts) or ('decrease' in mod_instruction_parts)) or (('Increase' in mod_instruction_parts) or ('Decrease' in mod_instruction_parts)):
                        if 'increase' in mod_instruction_parts or 'Increase' in mod_instruction_parts:
                            action_index = mod_instruction_parts.index('increase' if 'increase' in mod_instruction_parts else 'Increase')
                        elif 'decrease' in mod_instruction_parts or 'Decrease' in mod_instruction_parts:
                            action_index = mod_instruction_parts.index('decrease' if 'decrease' in mod_instruction_parts else 'Decrease')
                        action = mod_instruction_parts[action_index].lower()
                        attribute_name = mod_instruction_parts[action_index + 1]
                        change_value = int(mod_instruction_parts[-1].strip('.'))
                        mod_narr = f'{"+ " if action == "increase" else "- "}{line}'
                        narrator(mod_narr)
                        self.execute_attribute_modification(attribute_name, change_value if action == 'increase' else -change_value)
        
        def execute_attribute_modification(self, attribute_name, change_amount):
            """Apply the attribute modification to the partner."""
            current_value = self.partner.get_attribute_value(attribute_name)
            attribute_data = self.partner.attributes.get(attribute_name, {})
            # Fetch the attribute range or default to [0, 100]
            min_value, max_value = attribute_data.get('range', [0, 100])
            new_value = max(min(current_value + change_amount, max_value), min_value)
            self.partner.set_dynamic_attribute(attribute_name, new_value)
        
    def split_into_sentences(text):
        """Utility function to split text into sentences."""
        return [s.strip() for s in AutoScriptParser.SPLITTER.split(text) if s and not s.isspace()]
