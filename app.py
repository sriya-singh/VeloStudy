import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
import streamlit.components.v1 as components
import re
import os
from dotenv import load_dotenv
import html

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

def configure_genai():
    """Configure the Gemini AI with the API key."""
    if not API_KEY:
        st.error("API Key is missing. Please provide a valid Google API key.")
        return False
    try:
        genai.configure(api_key=API_KEY)
        return True
    except Exception as e:
        st.error(f"Error configuring Google API: {str(e)}")
        return False

def extract_text_from_pdf(pdf_file):
    """Extract text from uploaded PDF file."""
    try:
        pdf_reader = PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:  # Only add non-empty pages
                text += page_text + "\n"
        if not text.strip():
            st.warning("No text could be extracted from the PDF. Please ensure it's not scanned or image-based.")
            return None
        return text.strip()
    except Exception as e:
        st.error(f"Error reading PDF: {str(e)}")
        return None

def analyze_text_complexity(text):
    """Analyze text to determine appropriate mindmap complexity."""
    word_count = len(text.split())
    char_count = len(text)
    
    # Count sentences (rough estimation)
    sentence_count = len(re.findall(r'[.!?]+', text))
    
    # Count paragraphs (double newlines or significant line breaks)
    paragraph_count = len(re.split(r'\n\s*\n', text.strip()))
    
    # Identify potential headings/sections
    potential_headings = len(re.findall(r'^[A-Z][^.!?]*$', text, re.MULTILINE))
    
    # Calculate complexity score
    complexity_score = (
        (word_count / 100) * 0.4 +
        (sentence_count / 10) * 0.3 +
        (paragraph_count / 5) * 0.2 +
        (potential_headings / 3) * 0.1
    )
    
    return {
        'word_count': word_count,
        'char_count': char_count,
        'sentence_count': sentence_count,
        'paragraph_count': paragraph_count,
        'potential_headings': potential_headings,
        'complexity_score': complexity_score
    }

def determine_mindmap_depth(complexity_score):
    """Determine appropriate mindmap depth based on text complexity."""
    if complexity_score < 5:
        return {'max_levels': 3, 'detail_level': 'basic', 'expand_level': 2}
    elif complexity_score < 15:
        return {'max_levels': 4, 'detail_level': 'moderate', 'expand_level': 2}
    elif complexity_score < 30:
        return {'max_levels': 5, 'detail_level': 'detailed', 'expand_level': 1}
    else:
        return {'max_levels': 6, 'detail_level': 'comprehensive', 'expand_level': 1}

def chunk_text_intelligently(text, max_chunk_size=25000):
    """Intelligently chunk text while preserving context."""
    if len(text) <= max_chunk_size:
        return [text]
    
    # Try to split by paragraphs first
    paragraphs = re.split(r'\n\s*\n', text)
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) <= max_chunk_size:
            current_chunk += paragraph + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = paragraph + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def create_adaptive_prompt(text_analysis, mindmap_config):
    """Create a dynamic prompt based on text analysis."""
    detail_level = mindmap_config['detail_level']
    max_levels = mindmap_config['max_levels']
    
    base_prompt = f"""
    Create a hierarchical markdown mindmap from the following text with {detail_level} level of detail.
    Use up to {max_levels} levels of hierarchy (# for main topics, ## for subtopics, ### for sub-subtopics, etc.).
    
    Based on the text complexity:
    - Word count: {text_analysis['word_count']}
    - Estimated sections: {text_analysis['paragraph_count']}
    
    """
    
    if detail_level == 'basic':
        specific_instructions = """
        Focus on:
        - 3-5 main topics maximum
        - Key concepts and definitions
        - Essential relationships
        - Keep it concise and clear
        """
    elif detail_level == 'moderate':
        specific_instructions = """
        Focus on:
        - 4-7 main topics
        - Important subtopics with explanations
        - Key examples and details
        - Connections between concepts
        - Supporting evidence or data points
        """
    elif detail_level == 'detailed':
        specific_instructions = """
        Focus on:
        - 6-10 main topics
        - Comprehensive subtopic breakdown
        - Specific examples, case studies, or applications
        - Detailed explanations and context
        - Cross-references and relationships
        - Important quotes or key points
        """
    else:  # comprehensive
        specific_instructions = """
        Focus on:
        - Comprehensive topic coverage (8-15 main topics)
        - Extensive subtopic hierarchy
        - Detailed examples, case studies, and applications
        - In-depth explanations with context
        - Multiple perspectives or viewpoints
        - Supporting data, statistics, or evidence
        - Cross-references and complex relationships
        - Key quotes, definitions, and terminology
        """
    
    format_example = """
    Format the output exactly like this structure:
    # Main Topic 1
    ## Subtopic 1.1
    ### Detail 1.1.1
    - Key point 1
    - Key point 2
    #### Sub-detail (if needed for complex content)
    - Specific information
    ### Detail 1.1.2
    ## Subtopic 1.2
    # Main Topic 2
    """
    
    return base_prompt + specific_instructions + format_example + "\n\nText to analyze: {text}\n\nRespond only with the markdown mindmap, no additional text."

def create_mindmap_markdown(text):
    """Generate adaptive mindmap markdown using Gemini AI."""
    try:
        model = genai.GenerativeModel()
        
        # Analyze text complexity
        text_analysis = analyze_text_complexity(text)
        mindmap_config = determine_mindmap_depth(text_analysis['complexity_score'])
        
        # Display analysis info
        st.info(f"""
        **Text Analysis:**
        - Words: {text_analysis['word_count']:,}
        - Estimated complexity: {text_analysis['complexity_score']:.1f}
        - Mindmap detail level: {mindmap_config['detail_level'].title()}
        - Maximum hierarchy levels: {mindmap_config['max_levels']}
        """)
        
        # Chunk text if necessary
        chunks = chunk_text_intelligently(text, max_chunk_size=25000)
        
        if len(chunks) > 1:
            st.warning(f"Text split into {len(chunks)} chunks for processing. Combining results...")
            
            # Process each chunk and combine results
            all_mindmaps = []
            progress_bar = st.progress(0)
            
            for i, chunk in enumerate(chunks):
                prompt = create_adaptive_prompt(text_analysis, mindmap_config)
                response = model.generate_content(prompt.format(text=chunk))
                
                if response.text and response.text.strip():
                    all_mindmaps.append(response.text.strip())
                
                progress_bar.progress((i + 1) / len(chunks))
            
            # Combine and consolidate mindmaps
            combined_text = "\n\n".join(all_mindmaps)
            consolidation_prompt = f"""
            Consolidate the following mindmap sections into a single, coherent hierarchical mindmap.
            Remove duplicates, organize related topics together, and maintain the hierarchical structure.
            Keep the detail level as {mindmap_config['detail_level']} with up to {mindmap_config['max_levels']} levels.
            
            Mindmap sections to consolidate:
            {combined_text}
            
            Respond only with the consolidated markdown mindmap.
            """
            
            final_response = model.generate_content(consolidation_prompt)
            return final_response.text.strip() if final_response.text else None
            
        else:
            # Single chunk processing
            prompt = create_adaptive_prompt(text_analysis, mindmap_config)
            response = model.generate_content(prompt.format(text=text))
            
            if not response.text or not response.text.strip():
                st.error("Received empty response from Gemini AI")
                return None
                
            return response.text.strip()
            
    except Exception as e:
        st.error(f"Error generating mindmap: {str(e)}")
        return None

def create_markmap_html(markdown_content, mindmap_config):
    """Create HTML with enhanced Markmap visualization adapted to content complexity."""
    # Properly escape the markdown content
    escaped_content = markdown_content.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${').replace('"', '\\"')
    
    # Adaptive configuration based on complexity
    initial_expand = mindmap_config['expand_level']
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Interactive Mindmap</title>
        <style>
            body {{
                margin: 0;
                padding: 10px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
                background: #f5f5f5;
            }}
            #mindmap {{
                width: 100%;
                height: 650px;
                background: white;
                border: 2px solid #e0e0e0;
                border-radius: 12px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            .controls {{
                margin: 15px 0;
                text-align: center;
                background: white;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }}
            .controls button {{
                margin: 0 8px;
                padding: 10px 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 25px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                transition: all 0.3s ease;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
            }}
            .controls button:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
            }}
            .controls button:active {{
                transform: translateY(0);
            }}
            .loading {{
                display: flex;
                justify-content: center;
                align-items: center;
                height: 400px;
                font-size: 18px;
                color: #666;
            }}
            .error {{
                color: #d32f2f;
                text-align: center;
                padding: 20px;
                background: #ffebee;
                border-radius: 8px;
                margin: 20px;
            }}
        </style>
        <script src="https://unpkg.com/d3@7"></script>
        <script src="https://unpkg.com/markmap-lib@0.15.3/dist/browser/index.js"></script>
        <script src="https://unpkg.com/markmap-view@0.15.3/dist/browser/index.js"></script>
    </head>
    <body>
        <div class="controls">
            <button onclick="expandAll()">🔄 Expand All</button>
            <button onclick="collapseAll()">📁 Collapse All</button>
            <button onclick="fitView()">🎯 Fit View</button>
            <button onclick="resetZoom()">🔍 Reset Zoom</button>
            <button onclick="downloadSVG()">💾 Download SVG</button>
        </div>
        
        <div id="loading" class="loading">
            <div>🧠 Loading your mindmap...</div>
        </div>
        
        <svg id="mindmap" style="display: none;"></svg>
        
        <script>
            let mm;
            let rootData;
            let svg;
            
            // Wait for libraries to load
            function initializeMindmap() {{
                try {{
                    // Hide loading, show mindmap
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('mindmap').style.display = 'block';
                    
                    const markdown = `{escaped_content}`;
                    
                    // Verify markmap is available
                    if (typeof markmap === 'undefined') {{
                        throw new Error('Markmap library not loaded');
                    }}
                    
                    const {{ Transformer }} = markmap;
                    const {{ Markmap }} = markmap;
                    
                    const transformer = new Transformer();
                    const {{ root, features }} = transformer.transform(markdown);
                    rootData = root;
                    
                    svg = document.querySelector('#mindmap');
                    mm = new Markmap(svg, {{
                        maxWidth: 300,
                        color: (node) => {{
                            const colors = [
                                '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', 
                                '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F'
                            ];
                            return colors[node.depth % colors.length];
                        }},
                        paddingX: 15,
                        paddingY: 10,
                        autoFit: true,
                        initialExpandLevel: {initial_expand},
                        duration: 800,
                        spacingVertical: 15,
                        spacingHorizontal: 100,
                        fitRatio: 0.9,
                        pan: true,
                        zoom: true,
                    }});
                    
                    mm.setData(root);
                    mm.fit();
                    
                    console.log('Mindmap initialized successfully');
                    
                }} catch (error) {{
                    console.error('Error initializing mindmap:', error);
                    document.getElementById('loading').innerHTML = 
                        '<div class="error">❌ Error loading mindmap: ' + error.message + 
                        '<br><br>Please try refreshing the page or check your content format.</div>';
                }}
            }}
            
            // Initialize after a short delay to ensure libraries are loaded
            setTimeout(initializeMindmap, 1000);
            
            function expandAll() {{
                if (mm && rootData) {{
                    try {{
                        mm.setData(rootData, {{ autoFit: false }});
                        setTimeout(() => mm.fit(), 300);
                    }} catch (e) {{
                        console.error('Error expanding:', e);
                    }}
                }}
            }}
            
            function collapseAll() {{
                if (mm && rootData) {{
                    try {{
                        const collapsedData = JSON.parse(JSON.stringify(rootData));
                        function collapseNode(node) {{
                            if (node.children && node.children.length > 0) {{
                                node.payload = {{ ...node.payload, fold: 1 }};
                                node.children.forEach(collapseNode);
                            }}
                        }}
                        if (collapsedData.children) {{
                            collapsedData.children.forEach(collapseNode);
                        }}
                        mm.setData(collapsedData, {{ autoFit: false }});
                        setTimeout(() => mm.fit(), 300);
                    }} catch (e) {{
                        console.error('Error collapsing:', e);
                    }}
                }}
            }}
            
            function fitView() {{
                if (mm) {{
                    try {{
                        mm.fit();
                    }} catch (e) {{
                        console.error('Error fitting view:', e);
                    }}
                }}
            }}
            
            function resetZoom() {{
                if (mm) {{
                    try {{
                        mm.rescale(1);
                        mm.fit();
                    }} catch (e) {{
                        console.error('Error resetting zoom:', e);
                    }}
                }}
            }}
            
            function downloadSVG() {{
                try {{
                    const svgElement = document.getElementById('mindmap');
                    const svgData = new XMLSerializer().serializeToString(svgElement);
                    const svgBlob = new Blob([svgData], {{type: 'image/svg+xml;charset=utf-8'}});
                    const svgUrl = URL.createObjectURL(svgBlob);
                    const downloadLink = document.createElement('a');
                    downloadLink.href = svgUrl;
                    downloadLink.download = 'mindmap.svg';
                    document.body.appendChild(downloadLink);
                    downloadLink.click();
                    document.body.removeChild(downloadLink);
                    URL.revokeObjectURL(svgUrl);
                }} catch (e) {{
                    console.error('Error downloading SVG:', e);
                    alert('Error downloading SVG. Please try again.');
                }}
            }}
            
            // Handle window resize
            window.addEventListener('resize', function() {{
                if (mm) {{
                    setTimeout(() => mm.fit(), 100);
                }}
            }});
        </script>
    </body>
    </html>
    """
    return html_content


def create_flashcards(text, num_cards=10):
    """Generate flashcards from the text content."""
    try:
        model = genai.GenerativeModel()
        
        prompt = f"""
        Create {num_cards} high-quality flashcards from the following text.
        Focus on key concepts, definitions, important facts, and relationships.
        
        Format each flashcard as:
        CARD X:
        Q: [Question]
        A: [Answer]
        
        Make questions clear and specific. Keep answers concise but complete.
        Cover the most important topics from the text.
        
        Text: {text}
        """
        
        response = model.generate_content(prompt)
        
        if not response.text:
            return None
            
        # Parse flashcards
        cards = []
        card_blocks = response.text.split('CARD')[1:]  # Skip first empty element
        
        for block in card_blocks:
            lines = block.strip().split('\n')
            question = ""
            answer = ""
            
            for line in lines:
                if line.startswith('Q:'):
                    question = line[2:].strip()
                elif line.startswith('A:'):
                    answer = line[2:].strip()
            
            if question and answer:
                cards.append({"question": question, "answer": answer})
        
        return cards
        
    except Exception as e:
        st.error(f"Error generating flashcards: {str(e)}")
        return None

def create_summary(text, word_count=500):
    """Generate a summary with specified word count."""
    try:
        model = genai.GenerativeModel()
       
        # Determine summary type based on word count only
        if word_count < 100:
            summary_type = "concise"
        elif word_count < 300:
            summary_type = "brief"
        elif word_count < 600:
            summary_type = "moderate"
        else:
            summary_type = "detailed"
       
        prompt = f"""
        Create a {summary_type} summary of the following text in approximately {word_count} words.
       
        Guidelines:
        - Capture the main ideas and key points
        - Maintain logical flow and structure
        - Include important details, examples, or data as space allows
        - Use clear, concise language
        - Ensure the summary is self-contained and informative
       
        Target word count: {word_count} words
       
        Text to summarize: {text}
        """
       
        response = model.generate_content(prompt)
       
        if not response.text:
            return None
           
        summary = response.text.strip()
        actual_word_count = len(summary.split())
       
        return {
            "summary": summary,
            "actual_word_count": actual_word_count,
            "target_word_count": word_count
        }
       
    except Exception as e:
        st.error(f"Error generating summary: {str(e)}")
        return None

def create_quiz(text, num_questions=10, difficulty="medium"):
    """Generate an interactive quiz from the text."""
    try:
        model = genai.GenerativeModel()
        
        difficulty_instructions = {
            "easy": "Focus on basic facts, definitions, and main concepts. Make questions straightforward.",
            "medium": "Include analytical questions, relationships between concepts, and some application-based questions.",
            "hard": "Create challenging questions requiring critical thinking, analysis, and application of concepts."
        }
        
        prompt = f"""
        Create {num_questions} multiple-choice quiz questions from the following text.
        Difficulty level: {difficulty}
        {difficulty_instructions[difficulty]}
        
        Format each question as:
        QUESTION X:
        Q: [Question text]
        A) [Option A]
        B) [Option B]
        C) [Option C]
        D) [Option D]
        CORRECT: [A/B/C/D]
        EXPLANATION: [Brief explanation of why this is correct]
        
        Make sure:
        - Questions test understanding, not just memorization
        - All options are plausible
        - Cover different parts of the text
        - Explanations are helpful for learning
        
        Text: {text}
        """
        
        response = model.generate_content(prompt)
        
        if not response.text:
            return None
            
        # Parse quiz questions
        questions = []
        question_blocks = response.text.split('QUESTION')[1:]
        
        for block in question_blocks:
            lines = [line.strip() for line in block.strip().split('\n') if line.strip()]
            
            question_data = {
                "question": "",
                "options": [],
                "correct": "",
                "explanation": ""
            }
            
            for line in lines:
                if line.startswith('Q:'):
                    question_data["question"] = line[2:].strip()
                elif line.startswith(('A)', 'B)', 'C)', 'D)')):
                    question_data["options"].append(line)
                elif line.startswith('CORRECT:'):
                    question_data["correct"] = line[8:].strip()
                elif line.startswith('EXPLANATION:'):
                    question_data["explanation"] = line[12:].strip()
            
            if question_data["question"] and len(question_data["options"]) == 4:
                questions.append(question_data)
        
        return questions
        
    except Exception as e:
        st.error(f"Error generating quiz: {str(e)}")
        return None

def display_flashcards(cards):
    """Display interactive flashcards using Streamlit with optimized performance."""
    if not cards:
        st.error("No flashcards available.")
        return
    
    st.subheader(f"📚 Flashcards ({len(cards)} cards)")
    
    # Initialize session state only once with unique keys
    if 'flashcard_current_card' not in st.session_state:
        st.session_state.flashcard_current_card = 0
    if 'flashcard_show_answer' not in st.session_state:
        st.session_state.flashcard_show_answer = False
    if 'flashcard_stats' not in st.session_state:
        st.session_state.flashcard_stats = {"correct": 0, "incorrect": 0}
    
    # Ensure current_card is within bounds
    if st.session_state.flashcard_current_card >= len(cards):
        st.session_state.flashcard_current_card = 0
    
    current_card = cards[st.session_state.flashcard_current_card]
    
    # Card navigation info
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.metric("Card Progress", f"{st.session_state.flashcard_current_card + 1} / {len(cards)}")
    
    # Display card with container for better performance
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 30px;
        border-radius: 15px;
        margin: 20px 0;
        color: white;
        text-align: center;
        min-height: 200px;
        display: flex;
        align-items: center;
        justify-content: center;
    ">
        <div>
            <h3 style="margin-bottom: 20px;">{"Question" if not st.session_state.flashcard_show_answer else "Answer"}</h3>
            <p style="font-size: 18px; line-height: 1.6;">
                {current_card["question"] if not st.session_state.flashcard_show_answer else current_card["answer"]}
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Controls with unique keys to prevent conflicts
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        if st.button("⬅️ Previous", key="flashcard_prev_card"):
            if st.session_state.flashcard_current_card > 0:
                st.session_state.flashcard_current_card -= 1
                st.session_state.flashcard_show_answer = False
                st.rerun()
    
    with col2:
        if st.button("🔄 Flip Card", key="flashcard_flip_card"):
            st.session_state.flashcard_show_answer = not st.session_state.flashcard_show_answer
            st.rerun()
    
    with col3:
        if st.session_state.flashcard_show_answer:
            if st.button("✅ Got it right", key="flashcard_correct_answer"):
                st.session_state.flashcard_stats["correct"] += 1
                if st.session_state.flashcard_current_card < len(cards) - 1:
                    st.session_state.flashcard_current_card += 1
                    st.session_state.flashcard_show_answer = False
                    st.rerun()
    
    with col4:
        if st.session_state.flashcard_show_answer:
            if st.button("❌ Got it wrong", key="flashcard_wrong_answer"):
                st.session_state.flashcard_stats["incorrect"] += 1
                if st.session_state.flashcard_current_card < len(cards) - 1:
                    st.session_state.flashcard_current_card += 1
                    st.session_state.flashcard_show_answer = False
                    st.rerun()
    
    with col5:
        if st.button("➡️ Next", key="flashcard_next_card"):
            if st.session_state.flashcard_current_card < len(cards) - 1:
                st.session_state.flashcard_current_card += 1
                st.session_state.flashcard_show_answer = False
                st.rerun()
    
    # Stats display
    if st.session_state.flashcard_stats["correct"] + st.session_state.flashcard_stats["incorrect"] > 0:
        total_answered = st.session_state.flashcard_stats["correct"] + st.session_state.flashcard_stats["incorrect"]
        accuracy = (st.session_state.flashcard_stats["correct"] / total_answered) * 100
        
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Correct", st.session_state.flashcard_stats["correct"])
        with col2:
            st.metric("Incorrect", st.session_state.flashcard_stats["incorrect"])
        with col3:
            st.metric("Accuracy", f"{accuracy:.1f}%")

def display_quiz(questions):
    """Display interactive quiz interface with optimized performance."""
    if not questions:
        st.error("No quiz questions available.")
        return
    
    st.subheader(f"🧠 Interactive Quiz ({len(questions)} questions)")
    
    # Initialize session state with unique prefixes
    if 'quiz_current_question' not in st.session_state:
        st.session_state.quiz_current_question = 0
    if 'quiz_user_answers' not in st.session_state:
        st.session_state.quiz_user_answers = {}
    if 'quiz_is_submitted' not in st.session_state:
        st.session_state.quiz_is_submitted = False
    if 'quiz_show_results' not in st.session_state:
        st.session_state.quiz_show_results = False
    
    # Ensure current question is within bounds
    if st.session_state.quiz_current_question >= len(questions):
        st.session_state.quiz_current_question = 0
    
    if not st.session_state.quiz_show_results:
        # Quiz mode
        current_q = questions[st.session_state.quiz_current_question]
        
        # Progress
        progress = (st.session_state.quiz_current_question + 1) / len(questions)
        st.progress(progress)
        st.write(f"Question {st.session_state.quiz_current_question + 1} of {len(questions)}")
        
        # Question
        st.markdown(f"### {current_q['question']}")
        
        # Options with unique key
        answer_key = f"question_{st.session_state.quiz_current_question}"
        
        # Get current answer if exists
        current_answer_index = None
        if answer_key in st.session_state.quiz_user_answers:
            user_answer = st.session_state.quiz_user_answers[answer_key]
            for i, option in enumerate(current_q['options']):
                if option.startswith(user_answer):
                    current_answer_index = i
                    break
        
        selected = st.radio(
            "Choose your answer:",
            current_q['options'],
            key=f"quiz_radio_question_{st.session_state.quiz_current_question}",
            index=current_answer_index
        )
        
        if selected:
            st.session_state.quiz_user_answers[answer_key] = selected[0]  # Store A, B, C, or D
        
        # Navigation buttons
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.session_state.quiz_current_question > 0:
                if st.button("⬅️ Previous Question", key="quiz_prev_question"):
                    st.session_state.quiz_current_question -= 1
                    st.rerun()
        
        with col2:
            if st.session_state.quiz_current_question < len(questions) - 1:
                if st.button("➡️ Next Question", key="quiz_next_question"):
                    st.session_state.quiz_current_question += 1
                    st.rerun()
        
        with col3:
            # Check if all questions are answered
            answered_count = len(st.session_state.quiz_user_answers)
            if st.button(f"✅ Submit Quiz ({answered_count}/{len(questions)})", 
                        type="primary", 
                        key="quiz_submit_answers",
                        disabled=answered_count < len(questions)):
                st.session_state.quiz_is_submitted = True
                st.session_state.quiz_show_results = True
                st.rerun()
        
        # Show progress of answered questions
        if answered_count > 0:
            st.info(f"Progress: {answered_count}/{len(questions)} questions answered")
    
    else:
        # Results mode
        st.subheader("📊 Quiz Results")
        
        correct_answers = 0
        total_questions = len(questions)
        
        results_data = []
        
        for i, question in enumerate(questions):
            answer_key = f"question_{i}"
            user_answer = st.session_state.quiz_user_answers.get(answer_key, "")
            correct_answer = question['correct']
            is_correct = user_answer == correct_answer
            
            if is_correct:
                correct_answers += 1
            
            results_data.append({
                'question_num': i + 1,
                'question': question['question'],
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'is_correct': is_correct,
                'explanation': question['explanation']
            })
        
        # Overall score
        score_percentage = (correct_answers / total_questions) * 100
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Score", f"{correct_answers}/{total_questions}")
        with col2:
            st.metric("Percentage", f"{score_percentage:.1f}%")
        with col3:
            if score_percentage >= 80:
                st.success("Excellent! 🌟")
            elif score_percentage >= 60:
                st.info("Good job! 👍")
            else:
                st.warning("Keep studying! 📚")
        
        # Detailed results
        st.markdown("### Detailed Results")
        
        for result in results_data:
            status_icon = "✅" if result['is_correct'] else "❌"
            with st.expander(f"Question {result['question_num']}: {status_icon}"):
                st.write(f"**Q:** {result['question']}")
                st.write(f"**Your answer:** {result['user_answer']}")
                st.write(f"**Correct answer:** {result['correct_answer']}")
                st.write(f"**Explanation:** {result['explanation']}")
        
        # Reset quiz button
        if st.button("🔄 Retake Quiz", key="quiz_retake_button"):
            # Clear all quiz-related session state with specific keys
            keys_to_remove = ['quiz_current_question', 'quiz_user_answers', 'quiz_is_submitted', 'quiz_show_results']
            for key in keys_to_remove:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

def main():
    st.set_page_config(layout="wide", page_title="VeloStudy")
    
    st.markdown("""
    <h1 style="
        text-align: center;
        font-size: 3rem;
        font-weight: 800;
        margin-bottom: 0;
        background: linear-gradient(90deg, #00c6ff, #0072ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    ">
        VeloStudy
    </h1>
    <p style="
        text-align: center;
        color: #CCC;
        font-size: 1.2rem;
        margin-top: 6px;
    ">
        Your Complete Learning Companion
    </p>
    """, unsafe_allow_html=True)

    st.markdown("""
    ### Features:
    - 🧠 **Interactive Mindmaps**: Visualize content structure and relationships
    - 📄 **Smart Summaries**: Get concise summaries in your preferred length
    - 📚 **Flashcards**: Generate and practice with interactive flashcards
    - 🧠 **Interactive Quizzes**: Test your knowledge with adaptive difficulty
    - 📊 **Content Analysis**: Understand document complexity and structure
    - ⚡ **Large Document Support**: Handles extensive PDFs intelligently
    """)
    
    if not configure_genai():
        return

    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    
    if uploaded_file is not None:
        # Extract text only once and store in session state
        if 'extracted_text' not in st.session_state or st.session_state.get('current_file') != uploaded_file.name:
            with st.spinner("🔄 Processing PDF..."):
                text = extract_text_from_pdf(uploaded_file)
                if text:
                    st.session_state.extracted_text = text
                    st.session_state.current_file = uploaded_file.name
                    # Clear ALL previous data when new file is uploaded
                    keys_to_clear = ['file_stats', 'markdown_content', 'mindmap_config', 'summary_result', 'flashcards', 'quiz_questions']
                    for key in keys_to_clear:
                        if key in st.session_state:
                            del st.session_state[key]
                else:
                    st.error("Failed to extract text from PDF")
                    return
        
        text = st.session_state.extracted_text
        
        # Initialize active tab in session state if not exists
        if 'active_tab' not in st.session_state:
            st.session_state.active_tab = 0
        
        # Create proper tabs with Streamlit's native tab functionality
        tab_names = [
            "🧠 Interactive Mindmap", 
            "📝 Markdown Source", 
            "📄 Summary", 
            "📚 Flashcards", 
            "🧠 Quiz", 
            "📊 Analysis"
        ]
        
        # Use Streamlit's native tabs
        tabs = st.tabs(tab_names)
        
        # Tab 0: Interactive Mindmap
        with tabs[0]:
            st.subheader("🧠 Interactive Mindmap")
            
            # Mindmap options in main area
            st.markdown("### Mindmap Configuration")
            col1, col2 = st.columns(2)
            
            with col1:
                force_detail_level = st.selectbox(
                    "Detail Level",
                    ["Auto (Recommended)", "Basic", "Moderate", "Detailed", "Comprehensive"],
                    help="Force a specific detail level instead of auto-detection",
                    key="mindmap_detail_level"
                )
            
            with col2:
                show_analysis = st.checkbox("Show Text Analysis", value=True, key="mindmap_show_analysis")
            
            st.info("💡 **Tip**: Larger documents automatically get more detailed mindmaps!")
            
            # Generate button for mindmap
            if st.button("🎯 Generate Mindmap", type="primary", key="generate_mindmap_btn"):
                with st.spinner("Analyzing document and generating mindmap..."):
                    # Generate file stats
                    file_stats = analyze_text_complexity(text)
                    st.session_state.file_stats = file_stats
                    
                    # Determine mindmap configuration
                    if force_detail_level != "Auto (Recommended)":
                        level_map = {
                            "Basic": 'basic',
                            "Moderate": 'moderate', 
                            "Detailed": 'detailed',
                            "Comprehensive": 'comprehensive'
                        }
                        mindmap_config = {
                            'detail_level': level_map[force_detail_level],
                            'max_levels': {'basic': 3, 'moderate': 4, 'detailed': 5, 'comprehensive': 6}[level_map[force_detail_level]],
                            'expand_level': 2 if level_map[force_detail_level] in ['basic', 'moderate'] else 1
                        }
                        st.info(f"Using forced detail level: {force_detail_level}")
                    else:
                        mindmap_config = determine_mindmap_depth(file_stats['complexity_score'])
                    
                    st.session_state.mindmap_config = mindmap_config
                    
                    # Generate markdown content
                    markdown_content = create_mindmap_markdown(text)
                    if markdown_content:
                        st.session_state.markdown_content = markdown_content
                        st.success("Mindmap generated successfully!")
                    else:
                        st.error("Failed to generate mindmap")
                        return
            
            st.markdown("---")
            
            # Display mindmap if generated
            if 'markdown_content' in st.session_state and 'mindmap_config' in st.session_state:
                # Show analysis if requested
                if show_analysis and 'file_stats' in st.session_state:
                    file_stats = st.session_state.file_stats
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Words", f"{file_stats['word_count']:,}")
                    with col2:
                        st.metric("Characters", f"{file_stats['char_count']:,}")
                    with col3:
                        st.metric("Paragraphs", file_stats['paragraph_count'])
                    with col4:
                        st.metric("Complexity Score", f"{file_stats['complexity_score']:.1f}")
                
                markdown_content = st.session_state.markdown_content
                mindmap_config = st.session_state.mindmap_config
                
                st.markdown("*Use the controls below the mindmap to expand/collapse nodes and navigate*")
                html_content = create_markmap_html(markdown_content, mindmap_config)
                components.html(html_content, height=800, scrolling=True)
            else:
                st.info("👆 Click 'Generate Mindmap' to create an interactive visualization of your document.")
        
        # Tab 1: Markdown Source
        with tabs[1]:
            st.subheader("📝 Markdown Source")
            
            if 'markdown_content' in st.session_state:
                markdown_content = st.session_state.markdown_content
                
                st.text_area("Markdown Content", markdown_content, height=500)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="⬇️ Download Markdown",
                        data=markdown_content,
                        file_name=f"mindmap_{uploaded_file.name.replace('.pdf', '')}.md",
                        mime="text/markdown"
                    )
                with col2:
                    # Create a simple HTML export
                    simple_html = f"""
                    <!DOCTYPE html>
                    <html><head><title>Mindmap Export</title></head>
                    <body><pre>{html.escape(markdown_content)}</pre></body></html>
                    """
                    st.download_button(
                        label="⬇️ Download HTML",
                        data=simple_html,
                        file_name=f"mindmap_{uploaded_file.name.replace('.pdf', '')}.html",
                        mime="text/html"
                    )
            else:
                st.info("Generate a mindmap first to view the markdown source.")
        
        # Tab 2: Summary
        with tabs[2]:
            st.subheader("📄 Smart Summary")

            col1, col2 = st.columns(2)
            with col1:
                summary_length = st.slider("Summary length (words)", 100, 1000, 300, 50, key="summary_length_slider")
            with col2:
                if st.button("🎯 Generate Summary", type="primary", key="generate_summary_btn"):
                    # Use a unique key to prevent conflicts
                    summary_key = f"summary_result_{summary_length}_{hash(text[:100])}"
                    
                    with st.spinner("Creating summary..."):
                        summary_result = create_summary(text, summary_length)
                        if summary_result:
                            st.session_state[summary_key] = summary_result
                            st.session_state.current_summary_key = summary_key
                            st.success("Summary generated successfully!")
                        else:
                            st.error("Failed to generate summary. Please try again.")
            
            # Display current summary
            if hasattr(st.session_state, 'current_summary_key') and st.session_state.current_summary_key in st.session_state:
                result = st.session_state[st.session_state.current_summary_key]
                
                st.info(f"Generated summary: {result['actual_word_count']} words (target: {result['target_word_count']})")
                st.write(result['summary'])
                
                st.download_button(
                    label="⬇️ Download Summary",
                    data=result['summary'],
                    file_name=f"summary_{uploaded_file.name.replace('.pdf', '')}.txt",
                    mime="text/plain",
                    key="download_summary_btn"
                )

        # Tab 3: Flashcards
        with tabs[3]:
            st.subheader("📚 Flashcards")
            
            col1, col2 = st.columns(2)
            with col1:
                num_cards = st.slider("Number of flashcards", 5, 25, 10, key="flashcard_slider")
            with col2:
                if st.button("🎯 Generate Flashcards", type="primary", key="generate_flashcards_btn"):
                    with st.spinner("Creating flashcards..."):
                        cards = create_flashcards(text, num_cards)
                        if cards:
                            st.session_state.flashcards = cards
                            # Reset flashcard state when new cards are generated
                            flashcard_keys = ['flashcard_current_card', 'flashcard_show_answer', 'flashcard_stats']
                            for key in flashcard_keys:
                                if key in st.session_state:
                                    del st.session_state[key]
                            st.success(f"Generated {len(cards)} flashcards!")
                        else:
                            st.error("Failed to generate flashcards. Please try again.")
            
            if 'flashcards' in st.session_state and st.session_state.flashcards:
                display_flashcards(st.session_state.flashcards)
            else:
                st.info("👆 Click 'Generate Flashcards' to create interactive study cards.")
        
        # Tab 4: Quiz
        with tabs[4]:
            st.subheader("🧠 Interactive Quiz")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                num_questions = st.slider("Number of questions", 5, 20, 10, key="quiz_questions_slider")
            with col2:
                difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"], key="quiz_difficulty_select")
            with col3:
                if st.button("🎯 Generate Quiz", type="primary", key="generate_quiz_btn"):
                    with st.spinner("Creating quiz questions..."):
                        quiz_questions = create_quiz(text, num_questions, difficulty)
                        if quiz_questions:
                            st.session_state.quiz_questions = quiz_questions
                            # Reset quiz state when new quiz is generated
                            quiz_keys = ['quiz_current_question', 'quiz_user_answers', 'quiz_is_submitted', 'quiz_show_results']
                            for key in quiz_keys:
                                if key in st.session_state:
                                    del st.session_state[key]
                            st.success(f"Generated {len(quiz_questions)} quiz questions!")
                        else:
                            st.error("Failed to generate quiz questions. Please try again.")
            
            if 'quiz_questions' in st.session_state and st.session_state.quiz_questions:
                display_quiz(st.session_state.quiz_questions)
            else:
                st.info("👆 Click 'Generate Quiz' to create interactive questions.")
        
        # Tab 5: Analysis
        with tabs[5]:
            st.subheader("📊 Document Analysis")
            
            # Analysis button with debug info
            col1, col2 = st.columns([1, 3])
            with col1:
                analyze_clicked = st.button("🎯 Analyze Document", type="primary", key="analysis_document_btn")
            
            if analyze_clicked:
                with st.spinner("Analyzing document..."):
                    try:
                        file_stats = analyze_text_complexity(text)
                        st.session_state.file_stats = file_stats
                        
                        mindmap_config = determine_mindmap_depth(file_stats['complexity_score'])
                        st.session_state.mindmap_config = mindmap_config
                        
                        st.success("✅ Document analysis completed successfully!")
                        
                    except Exception as e:
                        st.error(f"❌ Analysis failed: {str(e)}")
            
            # Display analysis results
            if 'file_stats' in st.session_state and 'mindmap_config' in st.session_state:
                file_stats = st.session_state.file_stats
                mindmap_config = st.session_state.mindmap_config
                
                # Add some spacing
                st.markdown("---")
                st.markdown("### 📈 Analysis Results")
                
                # Quick metrics in a nice format
                st.markdown("#### 📊 Quick Metrics")
                metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                
                with metric_col1:
                    st.metric("Words", f"{file_stats['word_count']:,}")
                with metric_col2:
                    st.metric("Characters", f"{file_stats['char_count']:,}")
                with metric_col3:
                    st.metric("Paragraphs", file_stats['paragraph_count'])
                with metric_col4:
                    st.metric("Complexity", f"{file_stats['complexity_score']:.1f}")
                
                # Detailed analysis
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("#### 📈 Detailed Text Statistics")
                    st.json({
                        "Word Count": file_stats['word_count'],
                        "Character Count": file_stats['char_count'],
                        "Sentence Count": file_stats['sentence_count'],
                        "Paragraph Count": file_stats['paragraph_count'],
                        "Potential Headings": file_stats['potential_headings']
                    })
                
                with col2:
                    st.markdown("#### ⚙️ Recommended Mindmap Configuration")
                    st.json({
                        "Complexity Score": round(file_stats['complexity_score'], 2),
                        "Detail Level": mindmap_config['detail_level'].title(),
                        "Max Hierarchy Levels": mindmap_config['max_levels'],
                        "Initial Expand Level": mindmap_config['expand_level']
                    })
                    
            else:
                st.info("👆 Click 'Analyze Document' to view detailed statistics and configuration.")
                st.markdown("""
                **This analysis will provide:**
                - 📊 Document statistics (word count, paragraphs, etc.)
                - 🎯 Complexity scoring for optimal mindmap generation
                - ⚙️ Recommended mindmap configuration
                - 📝 Text structure analysis
                """)
                
if __name__ == "__main__":
    main()
