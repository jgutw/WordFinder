// Auto-search on Enter key
document.getElementById('wordInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        performSearch();
    }
});

// Auto-search on input change (debounced)
let searchTimeout;
document.getElementById('wordInput').addEventListener('input', function(e) {
    const word = e.target.value.trim();
    
    // Clear previous timeout
    clearTimeout(searchTimeout);
    
    // Only auto-search if word is at least 2 characters
    if (word.length >= 2) {
        searchTimeout = setTimeout(() => {
            performSearch();
        }, 800); // Wait 800ms after user stops typing
    } else {
        clearResults();
    }
});

let currentSearch = null;

async function performSearch() {
    const word = document.getElementById('wordInput').value.trim();
    
    if (!word) {
        showError('Please enter a word to search');
        return;
    }
    
    // Cancel previous search if still running
    if (currentSearch) {
        // Note: We can't actually cancel fetch, but we can ignore the result
    }
    
    // Show loading
    showLoading();
    hideError();
    hideResults();
    
    // Get selected languages
    const languageSelect = document.getElementById('languageSelect');
    const selectedLanguages = Array.from(languageSelect.selectedOptions)
        .map(opt => opt.value)
        .filter(val => val !== ''); // Remove empty "All Languages" option
    
    // Validate selection count
    if (selectedLanguages.length > 20) {
        showError('Maximum 20 languages allowed. Please select fewer languages.');
        hideLoading();
        return;
    }
    
    // Get options
    const options = {
        word: word,
        zipf: 2.5,
        minlen: 2,
        top: 12,
        max_langs: 10,  // Limit to 10 languages for faster response (if no selection)
        languages: selectedLanguages.length > 0 ? selectedLanguages : undefined,  // Only send if languages are selected
        morphemes: document.getElementById('enableMorphemes').checked,
        romanize: document.getElementById('showRomanization').checked,
        lemmatize: document.getElementById('enableLemmatize').checked
    };
    
    try {
        // Add timeout to fetch request (60 seconds)
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 60000);
        
        // Use absolute URL to avoid issues
        const apiUrl = window.location.origin + '/api/search';
        console.log('Fetching from:', apiUrl);
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(options),
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Search failed');
        }
        
        const data = await response.json();
        currentSearch = null;
        
        // Filter out languages with no results (already done server-side, but double-check)
        const filteredResults = {};
        for (const [lang, result] of Object.entries(data.results)) {
            const hasMain = result.inner_words_main && result.inner_words_main.length > 0;
            const hasRare = result.inner_words_rare && result.inner_words_rare.length > 0;
            if (hasMain || hasRare) {
                filteredResults[lang] = result;
            }
        }
        
        if (Object.keys(filteredResults).length === 0) {
            showError('No inner words found in any language. Try a different word or adjust settings.');
            hideLoading();
            return;
        }
        
        displayResults(data.input, filteredResults);
        hideLoading();
        loadHistory(); // Refresh history
        
    } catch (error) {
        console.error('Search error:', error);
        console.error('Error details:', {
            name: error.name,
            message: error.message,
            stack: error.stack
        });
        
        if (error.name === 'AbortError') {
            showError('Request timed out. Try searching with fewer languages or check your connection.');
        } else if (error.name === 'TypeError' && error.message.includes('fetch')) {
            showError('Failed to connect to server. Make sure the server is running on port 5001. Error: ' + error.message);
        } else if (error.message && error.message.includes('fetch')) {
            showError('Failed to connect to server. Make sure the server is running on port 5001.');
        } else {
            showError(error.message || 'An error occurred while searching. Check the browser console for details.');
        }
        hideLoading();
    }
}

function displayResults(inputWord, results) {
    const container = document.getElementById('resultsContainer');
    const title = document.getElementById('resultsTitle');
    
    title.textContent = `Results for "${inputWord}" (${Object.keys(results).length} languages)`;
    
    container.innerHTML = '';
    
    if (Object.keys(results).length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No results found</p></div>';
        document.getElementById('resultsSection').classList.remove('hidden');
        return;
    }
    
    // Sort languages alphabetically
    const sortedLangs = Object.keys(results).sort();
    
    sortedLangs.forEach(langName => {
        const result = results[langName];
        const card = createLanguageCard(langName, result);
        container.appendChild(card);
    });
    
    document.getElementById('resultsSection').classList.remove('hidden');
}

function createLanguageCard(langName, result) {
    const card = document.createElement('div');
    card.className = 'language-card';
    
    const header = document.createElement('div');
    header.className = 'language-header';
    header.innerHTML = `
        <span class="language-name">${escapeHtml(langName)}</span>
        <span class="language-code">${escapeHtml(result.code)}</span>
    `;
    card.appendChild(header);
    
    const translationInfo = document.createElement('div');
    translationInfo.className = 'translation-info';
    translationInfo.innerHTML = `
        <div class="translation-text">
            <strong>Translation:</strong> ${escapeHtml(result.translation)}
        </div>
        ${result.romanization ? `<div class="romanization">${escapeHtml(result.romanization)}</div>` : ''}
    `;
    card.appendChild(translationInfo);
    
    if (result.segments && result.segments.length > 0) {
        const segmentsDiv = document.createElement('div');
        segmentsDiv.className = 'segments';
        segmentsDiv.innerHTML = '<strong>Segments:</strong> ' + 
            result.segments.map(s => `<span>${escapeHtml(s)}</span>`).join('');
        card.appendChild(segmentsDiv);
    }
    
    const innerWordsDiv = document.createElement('div');
    innerWordsDiv.className = 'inner-words';
    
    // Main words
    if (result.inner_words_main && result.inner_words_main.length > 0) {
        const mainHeader = document.createElement('h4');
        mainHeader.textContent = 'Main Words:';
        innerWordsDiv.appendChild(mainHeader);
        
        const mainContainer = document.createElement('div');
        result.inner_words_main.forEach(word => {
            mainContainer.appendChild(createWordItem(word));
        });
        innerWordsDiv.appendChild(mainContainer);
    }
    
    // Rare words
    if (result.inner_words_rare && result.inner_words_rare.length > 0) {
        const rareHeader = document.createElement('h4');
        rareHeader.textContent = 'Rare Words:';
        innerWordsDiv.appendChild(rareHeader);
        
        const rareContainer = document.createElement('div');
        result.inner_words_rare.forEach(word => {
            rareContainer.appendChild(createWordItem(word));
        });
        innerWordsDiv.appendChild(rareContainer);
    }
    
    card.appendChild(innerWordsDiv);
    
    // Notes
    if (result.notes && result.notes.length > 0) {
        const notesDiv = document.createElement('div');
        notesDiv.className = 'notes';
        notesDiv.textContent = result.notes.join(' | ');
        card.appendChild(notesDiv);
    }
    
    return card;
}

function createWordItem(word) {
    const item = document.createElement('div');
    item.className = 'word-item';
    
    const token = document.createElement('span');
    token.className = 'word-token';
    token.textContent = word.token;
    
    const gloss = document.createElement('span');
    gloss.className = 'word-gloss';
    gloss.textContent = word.gloss_en || '(no translation)';
    
    const meta = document.createElement('div');
    meta.className = 'word-meta';
    const typeSpan = document.createElement('span');
    typeSpan.className = `word-type ${word.type}`;
    typeSpan.textContent = word.type;
    meta.appendChild(typeSpan);
    meta.appendChild(document.createTextNode(` Zipf: ${word.zipf}`));
    
    item.appendChild(token);
    item.appendChild(document.createTextNode(' → '));
    item.appendChild(gloss);
    item.appendChild(meta);
    
    return item;
}

function clearResults() {
    document.getElementById('resultsSection').classList.add('hidden');
    document.getElementById('resultsContainer').innerHTML = '';
}

function showLoading() {
    document.getElementById('loadingIndicator').classList.remove('hidden');
    document.getElementById('searchBtn').disabled = true;
}

function hideLoading() {
    document.getElementById('loadingIndicator').classList.add('hidden');
    document.getElementById('searchBtn').disabled = false;
}

function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

function hideError() {
    document.getElementById('errorMessage').classList.add('hidden');
}

function hideResults() {
    document.getElementById('resultsSection').classList.add('hidden');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// History functions
let historyVisible = false;

async function loadHistory() {
    try {
        const apiUrl = window.location.origin + '/api/history?limit=20';
        const response = await fetch(apiUrl);
        if (!response.ok) throw new Error('Failed to load history');
        
        const history = await response.json();
        displayHistory(history);
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

function displayHistory(history) {
    const container = document.getElementById('historyContainer');
    
    if (history.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No search history</p></div>';
        return;
    }
    
    container.innerHTML = '';
    
    history.forEach(item => {
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        
        const content = document.createElement('div');
        content.className = 'history-item-content';
        content.onclick = () => loadFromHistory(item);
        
        const word = document.createElement('div');
        word.className = 'history-word';
        word.textContent = item.word;
        
        const time = document.createElement('div');
        time.className = 'history-time';
        const date = new Date(item.timestamp);
        time.textContent = date.toLocaleString();
        
        content.appendChild(word);
        content.appendChild(time);
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'history-delete-btn';
        deleteBtn.textContent = 'Delete';
        deleteBtn.onclick = (e) => {
            e.stopPropagation(); // Prevent triggering loadFromHistory
            deleteHistoryItem(item.id);
        };
        
        historyItem.appendChild(content);
        historyItem.appendChild(deleteBtn);
        container.appendChild(historyItem);
    });
}

function loadFromHistory(item) {
    document.getElementById('wordInput').value = item.word;
    if (item.results && Object.keys(item.results).length > 0) {
        displayResults(item.word, item.results);
    } else {
        performSearch();
    }
}

function toggleHistory() {
    historyVisible = !historyVisible;
    const container = document.getElementById('historyContainer');
    const button = document.getElementById('toggleHistory');
    
    if (historyVisible) {
        container.classList.remove('hidden');
        button.textContent = 'Hide';
        loadHistory();
    } else {
        container.classList.add('hidden');
        button.textContent = 'Show';
    }
}

// Test server connection on page load
async function testConnection() {
    try {
        const response = await fetch(window.location.origin + '/api/health');
        if (response.ok) {
            console.log('✓ Server connection OK');
        } else {
            console.error('✗ Server health check failed');
        }
    } catch (error) {
        console.error('✗ Cannot connect to server:', error);
        showError('Cannot connect to server. Make sure it\'s running on port 5001.');
    }
}

// Load languages into dropdown
async function loadLanguages() {
    try {
        console.log('Loading languages...');
        const response = await fetch(window.location.origin + '/api/languages');
        if (!response.ok) {
            throw new Error(`Failed to load languages: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Languages loaded:', data.languages.length);
        
        const select = document.getElementById('languageSelect');
        if (!select) {
            console.error('Language select element not found');
            return;
        }
        
        // Clear all existing options
        select.innerHTML = '';
        
        // Add "All Languages" option first
        const allOption = document.createElement('option');
        allOption.value = '';
        allOption.textContent = 'All Languages (Default: First 10)';
        select.appendChild(allOption);
        
        // Add all languages
        data.languages.forEach(lang => {
            const option = document.createElement('option');
            option.value = lang.code;
            option.textContent = lang.name;
            select.appendChild(option);
        });
        
        console.log('Languages added to dropdown');
        
        // Update selected count display
        updateSelectedCount();
        
        // Add change listener to update count and enforce limit (only once)
        if (!select.hasAttribute('data-listener-added')) {
            select.addEventListener('change', function(e) {
                const selected = Array.from(this.selectedOptions).filter(opt => opt.value !== '');
                if (selected.length > 20) {
                    // Remove the last selected option
                    const lastSelected = selected[selected.length - 1];
                    lastSelected.selected = false;
                    alert('Maximum 20 languages allowed. Please deselect some languages first.');
                }
                updateSelectedCount();
            });
            select.setAttribute('data-listener-added', 'true');
        }
    } catch (error) {
        console.error('Error loading languages:', error);
        const select = document.getElementById('languageSelect');
        if (select) {
            select.innerHTML = '<option value="">Error loading languages</option>';
        }
    }
}

function updateSelectedCount() {
    const select = document.getElementById('languageSelect');
    const selected = Array.from(select.selectedOptions).filter(opt => opt.value !== '');
    const countDiv = document.getElementById('selectedCount');
    
    if (selected.length === 0) {
        countDiv.textContent = '';
    } else if (selected.length > 20) {
        countDiv.textContent = '⚠ Max 20';
        countDiv.style.color = '#f44336';
    } else {
        countDiv.textContent = `${selected.length}/20 selected`;
        countDiv.style.color = '#667eea';
    }
}

// Delete history item
async function deleteHistoryItem(id) {
    if (!confirm('Are you sure you want to delete this search from history?')) {
        return;
    }
    
    try {
        const response = await fetch(window.location.origin + `/api/history/${id}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete');
        
        // Reload history
        loadHistory();
    } catch (error) {
        console.error('Error deleting history item:', error);
        showError('Failed to delete history item');
    }
}

// Load languages and history on page load
// Wait for DOM to be fully loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        testConnection();
        loadLanguages();
        loadHistory();
    });
} else {
    // DOM is already loaded
    testConnection();
    loadLanguages();
    loadHistory();
}

