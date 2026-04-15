This project will be a data warehouse and API for Dutch company data. 

Basic information will be scraped or retrieved from the KVK search API. Initially I will insert some data manually and leave the implementation of this scraper for the future. This data will contain names, kvk numbers and (dutch) addresses or locations.

On request (using an api call) a company and its data can be enriched. Multiple enrichment methods exist. Some examples are:

- Retrieving GPS coordinates for a company's address(es) 
- Using serper to perform a google search using its kvk number to try and locate the URLs associated with this company
- Using playwright or just plain requests to retrieve the website and store the html on the server
- Using an LLM integration (probably OpenAI or Claude) to extract information from the website

The data can be queried using an API, and an API token is required. This that can be generated. API calls are logged and stored because this will be a paid API.

The database is a PostgreSQL and a Redis queue. Create a docker-compose file for these. I will run this locally for now.

The API must expose an endpoint that places a company in an enrichment queue. A worker takes a request from the queue
