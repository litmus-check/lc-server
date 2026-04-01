Use Python 3.12.9
```
virtualenv venv --python=python3.12.9
./venv/Scripts/activate
```

Install qualium_browser in editable mode:
``` 
cd qualium_browser
pip install -e .
```

Install dependencies:
```
pip install -r requirements.txt
```


Install playwright:
```
npx playwright install
```

Install python-dotenv:
```
pip install python-dotenv
```

Install plyawright browsers:
```
pip install playwright
playwright install
playwright install-deps
```
## Turn on Redis container (local)

## Build Docker image
cd LitmusAgent
docker build -t litmus-test-runner .

## Run Python Flask app
cd src
python app.py

