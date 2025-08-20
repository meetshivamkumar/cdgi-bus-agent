# app.py
import os
import json
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client  # <-- ADDED IMPORT for WhatsApp
from openai import OpenAI
from dotenv import load_dotenv

from tools import tools_schema, available_functions

load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Initialize the Twilio REST client (needed for sending WhatsApp messages)
# It automatically uses the TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN from your .env file
twilio_client = Client()

# --- Configuration ---
conversations = {}

LANG_CONFIG = {
    'en-US': {'voice': 'Polly.Joanna', 'greeting': 'Welcome to the Chameli Devi Group of Institutions bus service. How can I help you find your bus today?'},
    'hi-IN': {'voice': 'Polly.Aditi', 'greeting': 'चमेली देवी ग्रुप ऑफ इंस्टीट्यूशंस बस सेवा में आपका स्वागत है। मैं आपकी बस ढूंढने में कैसे मदद कर सकती हूँ?'}
}

# A single, detailed system prompt for the AI
AI_SYSTEM_PROMPT = """You are a helpful AI assistant for the Chameli Devi Group of Institutions in Indore.
Your official name is the CDGI Bus Route Assistant.
Your goal is to find the correct bus for a student based on their stop name.
You MUST use the 'find_bus_for_stop' tool to get information from the official schedule. Do not make up bus details.
When you find the information, present it clearly to the student in a friendly, conversational way.
If responding via voice call, keep your answers concise.
If responding via WhatsApp, you can format the information nicely with line breaks.
If a stop is not found, politely ask the student to repeat the stop name.
Always respond in the language of the user's query (Hindi or English)."""


# =================================================================================
# === VOICE CALL ROUTES (Your existing, working code) ============================
# =================================================================================

@app.route("/voice", methods=['POST'])
def handle_call():
    """Handles the start of the call and language selection."""
    response = VoiceResponse()
    call_sid = request.values.get('CallSid')
    
    if 'Digits' in request.values:
        choice = request.values['Digits']
        lang_code = 'en-US' if choice == '1' else 'hi-IN' if choice == '2' else None
        if not lang_code:
            response.say("Invalid selection.", language='en-US')
            response.redirect('/voice')
            return str(response)

        conversations[call_sid] = {
            'language': lang_code,
            'history': [{"role": "system", "content": AI_SYSTEM_PROMPT}]
        }
        
        greeting = LANG_CONFIG[lang_code]['greeting']
        gather = Gather(input='speech', action=f'/respond?lang={lang_code}', speechTimeout='auto', language=lang_code)
        gather.say(greeting, voice=LANG_CONFIG[lang_code]['voice'], language=lang_code)
        response.append(gather)
        response.redirect(f'/respond?lang={lang_code}')

    else:
        gather = Gather(num_digits=1, action='/voice', method='POST')
        gather.say('For English, press 1.', language='en-US')
        gather.say('हिंदी के लिए, 2 दबाएँ।', language='hi-IN', voice='Polly.Aditi')
        response.append(gather)
        response.redirect('/voice')

    return str(response)


@app.route("/respond", methods=['POST'])
def respond():
    """Handles the back-and-forth voice conversation."""
    response = VoiceResponse()
    call_sid = request.values.get('CallSid')
    lang_code = request.args.get('lang', 'en-US')

    if call_sid not in conversations:
        response.say("Sorry, there was a system error. Please call again.", language=lang_code)
        response.hangup()
        return str(response)

    if 'SpeechResult' in request.values and request.values['SpeechResult']:
        user_speech = request.values['SpeechResult']
        conversations[call_sid]['history'].append({"role": "user", "content": user_speech})
        
        ai_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=conversations[call_sid]['history'],
            tools=tools_schema,
            tool_choice="auto"
        )
        response_message = ai_response.choices[0].message
        conversations[call_sid]['history'].append(response_message)

        if response_message.tool_calls:
            tool_call = response_message.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            function_to_call = available_functions[function_name]
            function_response = function_to_call(**function_args)
            
            conversations[call_sid]['history'].append({
                "tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": function_response,
            })

            final_response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=conversations[call_sid]['history']
            )
            final_text = final_response.choices[0].message.content
            conversations[call_sid]['history'].append({"role": "assistant", "content": final_text})
            response.say(final_text, voice=LANG_CONFIG[lang_code]['voice'], language=lang_code)
        else:
            text_response = response_message.content
            response.say(text_response, voice=LANG_CONFIG[lang_code]['voice'], language=lang_code)

    gather = Gather(input='speech', action=f'/respond?lang={lang_code}', speechTimeout='auto', language=lang_code)
    response.append(gather)

    return str(response)


# =================================================================================
# === NEW WHATSAPP ROUTE ==========================================================
# =================================================================================

@app.route("/whatsapp", methods=['POST'])
def handle_whatsapp():
    """Handles incoming WhatsApp messages."""
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    twilio_sandbox_number = request.values.get('To', '')
    
    print(f"Incoming WhatsApp message from {from_number}: {incoming_msg}")

    # Create a simple, short-lived message history for this interaction
    messages = [
        {"role": "system", "content": AI_SYSTEM_PROMPT},
        {"role": "user", "content": incoming_msg}
    ]
    
    # Call OpenAI with function calling enabled
    ai_response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        tools=tools_schema,
        tool_choice="auto"
    )
    response_message = ai_response.choices[0].message
    
    if response_message.tool_calls:
        tool_call = response_message.tool_calls[0]
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        function_to_call = available_functions[function_name]
        function_response = function_to_call(**function_args)
        
        messages.append(response_message) # Append the AI's decision to call a tool
        messages.append({
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": function_name,
            "content": function_response,
        })
        
        final_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        final_text = final_response.choices[0].message.content
    else:
        final_text = response_message.content

    # Send the final response back to the user via WhatsApp
    twilio_client.messages.create(
        from_=twilio_sandbox_number,
        body=final_text,
        to=from_number
    )
    
    # Return an empty 204 response to Twilio to acknowledge receipt of the message
    return ('', 204)


# =================================================================================
# === MAIN EXECUTION ==============================================================
# =================================================================================

if __name__ == "__main__":
    app.run(debug=True, port=5000)