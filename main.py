import requests
import time
from flask import Flask, jsonify, request, render_template, redirect, url_for
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import math

class LeaderboardScraper:
    def __init__(self, base_url, leaderboard_id, per_page=30):
        self.base_url = base_url
        self.leaderboard_id = leaderboard_id
        self.per_page = per_page
        self.total_pages = self.get_total_pages()
        self.progress = 0
        self.cached_results = None

    def get_total_pages(self):
        url = f"{self.base_url}/{self.leaderboard_id}/assessmentnewround"
        params = {
            "page": 1,
            "per_page": self.per_page,
            "undefined": "true"
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and 'total' in data['data']:
                total_items = data['data']['total']
                return math.ceil(total_items / self.per_page)
        print(f"Failed to get total pages for leaderboard {self.leaderboard_id}")
        return 0

    def fetch_page(self, page):
        url = f"{self.base_url}/{self.leaderboard_id}/assessmentnewround"
        params = {
            "page": page,
            "per_page": self.per_page,
            "undefined": "true"
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and 'data' in data['data']:
                return data['data']['data']
            else:
                print(f"Unexpected data structure on page {page}")
        else:
            print(f"Failed to fetch page {page}. Status code: {response.status_code}")
        return []

    def fetch_all_pages(self):
        if self.cached_results:
            return self.cached_results

        all_data = []
        self.progress = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_page = {executor.submit(self.fetch_page, page): page 
                              for page in range(1, self.total_pages + 1)}
            for future in as_completed(future_to_page):
                page = future_to_page[future]
                try:
                    data = future.result()
                    all_data.extend(data)
                    self.progress += 1
                    print(f"Fetched page {page}/{self.total_pages} for leaderboard {self.leaderboard_id}")
                except Exception as exc:
                    print(f"Page {page} generated an exception: {exc}")
                time.sleep(0.2)  # Add a small delay to avoid overwhelming the API

        self.cached_results = all_data
        return all_data

app = Flask(__name__)

leaderboards = {}  # Dictionary to store leaderboard IDs and their total pages
scraper_instances = {}

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        leaderboard_id = request.form.get('leaderboard_id')
        if leaderboard_id and leaderboard_id not in leaderboards:
            base_url = 'https://unstop.com/api/public/live-leaderboard'
            scraper = LeaderboardScraper(base_url, leaderboard_id)
            leaderboards[leaderboard_id] = scraper.total_pages
            scraper_instances[leaderboard_id] = scraper

        return redirect(url_for('home'))
    return render_template('index.html', leaderboards=leaderboards)

@app.route('/combined/<leaderboard_id>')
def combined_results(leaderboard_id):
    if leaderboard_id not in scraper_instances:
        return jsonify({"error": "Leaderboard ID not found"}), 404

    scraper = scraper_instances[leaderboard_id]
    result = scraper.fetch_all_pages()
    return jsonify(result)

@app.route('/progress/<leaderboard_id>')
def get_progress(leaderboard_id):
    if leaderboard_id not in scraper_instances:
        return jsonify({"error": "Leaderboard ID not found"}), 404

    scraper = scraper_instances[leaderboard_id]
    progress = (scraper.progress / scraper.total_pages) * 100
    return jsonify({"progress": progress, "total_pages": scraper.total_pages})

@app.route('/full_api/<leaderboard_id>')
def full_api_response(leaderboard_id):
    if leaderboard_id not in scraper_instances:
        return jsonify({"error": f"Leaderboard ID {leaderboard_id} not found"}), 404

    scraper = scraper_instances[leaderboard_id]
    try:
        if scraper.progress < scraper.total_pages:
            return jsonify({"error": "Data is still being fetched. Please try again later."}), 202
        result = scraper.fetch_all_pages()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/view_full_api/<leaderboard_id>')
def view_full_api(leaderboard_id):
    if leaderboard_id not in scraper_instances:
        return render_template('error.html', message=f"Leaderboard ID {leaderboard_id} not found"), 404
    return render_template('full_api_view.html', leaderboard_id=leaderboard_id)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)