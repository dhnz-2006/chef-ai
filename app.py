import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
from xml.etree.ElementTree import ParseError
from urllib.parse import urlparse, parse_qs
import ollama
import os
import json

# Configuration
client = ollama.Client()
model = "llama3.2:1b"
SAVE_DIR = "saved_outputs"
os.makedirs(SAVE_DIR, exist_ok=True)

# Streamlit layout
st.set_page_config(page_title="🍳 Recipe Extractor", layout="wide")
st.title("🍽️ Cooking Recipe Extractor")

# Sidebar: Show saved recipes
with st.sidebar:
    st.markdown("## 📁 Saved Recipes")
    recipe_files = [f for f in os.listdir(SAVE_DIR) if f.endswith(".json")]
    if recipe_files:
        for recipe_file in recipe_files:
            recipe_name = os.path.splitext(recipe_file)[0]
            with st.expander(recipe_name.title()):
                try:
                    with open(os.path.join(SAVE_DIR, recipe_file), "r", encoding="utf-8") as f:
                        saved_steps = json.load(f)
                        for idx, step in enumerate(saved_steps, 1):
                            st.markdown(
                                f"""
                                <div style="
                                    background-color: #f1f2f6;
                                    padding: 0.7rem;
                                    border-left: 5px solid #00cec9;
                                    border-radius: 8px;
                                    margin-bottom: 8px;
                                ">
                                    <b style="color:#2d3436;">Step {idx}</b>: <span style="color:#2d3436;">{step}</span>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
                except Exception as e:
                    st.error(f"⚠️ Error loading {recipe_name}: {e}")
    else:
        st.info("No saved recipes found.")

# Input area
st.markdown("Paste a YouTube video link in Tamil or English. The app will extract clean step-by-step cooking instructions.")
video_url = st.text_input("🔗 YouTube Video URL", placeholder="e.g., https://www.youtube.com/watch?v=e04HY19AJfU")
recipe_name = st.text_input("📌 Recipe Name", placeholder="e.g., Tomato Rice")

if st.button("Extract Recipe"):
    if not video_url or not recipe_name:
        st.warning("⚠️ Please enter both the video URL and the recipe name.")
        st.stop()

    with st.spinner("🔍 Processing video and extracting steps..."):
        try:
            # Get video ID
            query = urlparse(video_url)
            if query.hostname == 'youtu.be':
                video_id = query.path[1:]
            elif query.hostname in ('www.youtube.com', 'youtube.com'):
                video_id = parse_qs(query.query)['v'][0]
            else:
                st.error("❌ Invalid YouTube URL.")
                st.stop()

            # Fetch transcript
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
            try:
                transcript = transcripts.find_transcript([
                                            'en',   # English
                                            'ta',   # Tamil
                                            'hi',   # Hindi
                                            'te',   # Telugu
                                            'ml',   # Malayalam
                                            'kn',   # Kannada
                                            'mr',   # Marathi
                                            'gu',   # Gujarati
                                            'bn',   # Bengali
                                            'pa',   # Punjabi
                                            'ur',   # Urdu
                                        ])

            except NoTranscriptFound:
                major_languages = ['en', 'ta', 'hi', 'te', 'ml', 'kn', 'mr', 'gu', 'bn', 'pa', 'ur']
                transcript = next((t for t in transcripts if t.language_code in major_languages), None)
                if not transcript:
                    raise NoTranscriptFound(video_id, major_languages, transcripts)


            # Limit to first 4 minutes
            srt = transcript.fetch()
            filtered_srt = [entry for entry in srt if entry.start <= 240]
            original_text = " ".join(entry.text for entry in filtered_srt)

            # Translate Tamil to English if needed
            if transcript.language_code != 'en':
                st.info("🔁 Translating English...")
                translation_prompt = (
    "You are a smart language translator assistant.\n\n"
    "Your task is to translate a cooking video transcript into clear, simple English. "
    "The transcript may be in any language (e.g., Tamil, Hindi, Telugu, Malayalam, etc.).\n\n"
    "Translate ONLY the cooking-related content. Exclude:\n"
    "- Greetings, jokes, and personal introductions\n"
    "- Brand mentions, promotional content, or background music descriptions\n"
    "- Tips, comparisons, or commentary\n"
    "- Repetitions or casual talk\n\n"
    "Translation must be:\n"
    "- Clear and accurate\n"
    "- Focused only on the cooking actions, ingredients, and instructions\n"
    "- In natural, neutral English\n"
    "- Free of grammar or spelling errors\n\n"
    "DO NOT add anything new. DO NOT summarize. Just return the translated cooking process in the same tone and structure as the original.\n\n"
    f"Transcript:\n{original_text}"
                )
                english_text = client.generate(model=model, prompt=translation_prompt).response
            else:
                english_text = original_text

            # Extract instructions
            st.info("🤖 Extracting cooking instructions...")
            instruction_prompt = (
    "You are a smart assistant designed to extract detailed, actionable cooking instructions from a transcript of a cooking video.\n\n"
    "Your goal is to extract only the essential cooking instructions in the correct chronological order. Each step must describe a specific action, ingredient, and method, written clearly in simple English.\n\n"
    "Avoid small talk, greetings, brand names, commentary, tips, or repetition. Ignore background narration and casual conversation. Focus ONLY on the actual steps used to prepare the food or dish.\n\n"
    "Each instruction should:\n"
    "- Begin with a verb (e.g., 'Chop', 'Boil', 'Add')\n"
    "- Include the ingredient(s) or item(s) being used\n"
    "- Mention any quantity or condition if stated (e.g., '2 cups', 'until golden brown')\n"
    "- Be a single, clear sentence (max ~25 words)\n\n"

   " Your response must only be:"
"- One line per instruction"
"- No numbering, no quotes, no brackets"
"- No steps =, no Python formatting, no bullet points"

"Example output:"
'Chop two onions finely '
'Heat oil in a pan '
'Add chopped onions and sauté until golden brown'  
'Add tomatoes and cook until soft '


    "**Strict Guidelines:**\n"
    "- Do NOT return anything outside this list.\n"
    "- Do NOT include extra commentary, explanations, or print statements.\n"
    "- Do NOT wrap in triple quotes, markdown, or code formatting.\n"
    "- The list should be well-formatted, valid Python syntax.\n"
    "- If multiple dishes are made, include all steps sequentially.\n"
    "- Do not skip repeated but essential steps (like stirring, boiling, resting, etc.)\n\n"
    "Now read the following transcript and extract the steps list from it:\n\n"
            + english_text + recipe_name +"is the dish so add the steps accordingly which ever you know too, not just from the trasncript and fill in the steps somehow"
            )
            response_text = client.generate(model=model, prompt=instruction_prompt).response.strip()
            lines = response_text.strip().split("\n")
            steps = [line.strip() for line in lines if line.strip()]

            # Save the recipe using its name
            safe_filename = "".join(c for c in recipe_name if c.isalnum() or c in " _-").rstrip()
            save_path = os.path.join(SAVE_DIR, f"{safe_filename}.json")
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(steps, f, indent=2)

            st.success(f"✅ '{recipe_name}' extracted and saved!")

            for idx, step in enumerate(steps, 1):
                st.markdown(
                    f"""
                    <div style="
                        background-color: #f8f9fa;
                        padding: 1rem;
                        border-left: 5px solid #00b894;
                        border-radius: 8px;
                        margin-bottom: 10px;
                    ">
                        <h4 style="margin:0; color:#2d3436;">Step {idx}</h4>
                        <p style="margin:5px 0 0; color:#2d3436;">{step}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        except NoTranscriptFound:
            st.error("❌ No transcript found (Tamil or English).")
        except TranscriptsDisabled:
            st.error("❌ Transcripts are disabled for this video.")
        except ParseError:
            st.error("❌ YouTube transcript fetch failed due to XML issue.")
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")
