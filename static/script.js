class NewsBriefingApp {
    constructor() {
        this.API_BASE_URL = 'http://localhost:8000';
        this.STORAGE_KEY = 'news_briefing_feeds';
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadSavedFeeds();
    }

    bindEvents() {
        document.getElementById('briefingForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.generateBriefing();
        });

        document.getElementById('clearBtn').addEventListener('click', () => {
            this.clearForm();
        });

        // Auto-save feeds as user types
        document.getElementById('feedUrls').addEventListener('input', () => {
            this.saveFeeds();
        });

        // Event listener for the article count slider to update the label
        const maxArticlesSlider = document.getElementById('maxArticles');
        const maxArticlesValue = document.getElementById('maxArticlesValue');
        maxArticlesSlider.addEventListener('input', (e) => {
            maxArticlesValue.textContent = e.target.value;
        });
    }

    loadSavedFeeds() {
        const savedFeeds = localStorage.getItem(this.STORAGE_KEY);
        if (savedFeeds) {
            document.getElementById('feedUrls').value = savedFeeds;
        }
    }

    saveFeeds() {
        const feeds = document.getElementById('feedUrls').value;
        if (feeds.trim()) {
            localStorage.setItem(this.STORAGE_KEY, feeds);
        }
    }

    clearForm() {
        document.getElementById('feedUrls').value = '';
        document.getElementById('voiceSelect').selectedIndex = 0;
        document.getElementById('formatSelect').selectedIndex = 0;
        // Reset the slider and its display value
        const maxArticlesSlider = document.getElementById('maxArticles');
        maxArticlesSlider.value = 3;
        document.getElementById('maxArticlesValue').textContent = '3';

        localStorage.removeItem(this.STORAGE_KEY);
        this.hideAllMessages();
    }

    hideAllMessages() {
        document.getElementById('loadingDiv').classList.remove('show');
        document.getElementById('errorDiv').classList.remove('show');
        document.getElementById('resultDiv').classList.remove('show');
    }

    showLoading() {
        this.hideAllMessages();
        document.getElementById('loadingDiv').classList.add('show');
        document.getElementById('generateBtn').disabled = true;
    }

    hideLoading() {
        document.getElementById('loadingDiv').classList.remove('show');
        document.getElementById('generateBtn').disabled = false;
    }

    showError(message) {
        this.hideLoading();
        document.getElementById('errorMessage').textContent = message;
        document.getElementById('errorDiv').classList.add('show');
    }

    showResult(data) {
        this.hideLoading();
        
        const statsDiv = document.getElementById('resultStats');
        statsDiv.innerHTML = `
            <div class="stat">
                <div class="stat-value">${Math.round(data.audio_length_seconds)}s</div>
                <div class="stat-label">Duration</div>
            </div>
            <div class="stat">
                <div class="stat-value">${data.articles_count}</div>
                <div class="stat-label">Articles</div>
            </div>
            <div class="stat">
                <div class="stat-value">${data.sources.length}</div>
                <div class="stat-label">Sources</div>
            </div>
            <div class="stat">
                <div class="stat-value">${data.characters_used}</div>
                <div class="stat-label">Characters</div>
            </div>
        `;

        const audioPlayer = document.getElementById('audioPlayer');
        // Prepend the base URL if the path is relative
        audioPlayer.src = data.audio_url.startsWith('http') ? data.audio_url : this.API_BASE_URL + data.audio_url;

        document.getElementById('transcriptContent').textContent = data.briefing_text;

        const resultDiv = document.getElementById('resultDiv');
        resultDiv.classList.add('show', 'fade-in');
        resultDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    parseFeedUrls(input) {
        return input
            .split('\n')
            .map(url => url.trim())
            .filter(url => url && (url.startsWith('http://') || url.startsWith('https://')));
    }

    async generateBriefing() {
        const feedUrls = document.getElementById('feedUrls').value.trim();
        
        if (!feedUrls) {
            this.showError('Please enter at least one RSS feed URL');
            return;
        }

        const feeds = this.parseFeedUrls(feedUrls);
        
        if (feeds.length === 0) {
            this.showError('Please enter valid RSS feed URLs (must start with http:// or https://)');
            return;
        }

        this.saveFeeds();
        this.showLoading();

        // Added max_articles_per_feed to the request payload
        const requestData = {
            feeds: feeds,
            voice_id: document.getElementById('voiceSelect').value,
            audio_format: document.getElementById('formatSelect').value,
            max_articles_per_feed: parseInt(document.getElementById('maxArticles').value, 10)
        };

        try {
            const response = await fetch(`${this.API_BASE_URL}/generate-briefing`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            if (!response.ok) {

                throw new Error(data.detail || `HTTP error! status: ${response.status}`);
            }
            
            this.showResult(data);

        } catch (error) {
            console.error('Error generating briefing:', error);
            let errorMessage = 'Failed to generate briefing. ';
            
            if (error.message.includes('Failed to fetch')) {
                errorMessage += 'Could not connect to the server. Please make sure it is running on http://localhost:8000';
            } else {
                errorMessage += error.message;
            }
            
            this.showError(errorMessage);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new NewsBriefingApp();
});