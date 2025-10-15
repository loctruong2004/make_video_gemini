import requests
import os

url = "https://api.minimax.io/v1/video_generation"
api_key = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiJCIE4iLCJVc2VyTmFtZSI6IkIgTiIsIkFjY291bnQiOiIiLCJTdWJqZWN0SUQiOiIxOTExNzM4MzY0OTI3Njc3Mjk0IiwiUGhvbmUiOiIiLCJHcm91cElEIjoiMTkxMTczODM2NDkyMzQ4MjIzMCIsIlBhZ2VOYW1lIjoiIiwiTWFpbCI6ImN0eUBoYWloYXkubmV0IiwiQ3JlYXRlVGltZSI6IjIwMjUtMTAtMTEgMTI6NTY6MDgiLCJUb2tlblR5cGUiOjEsImlzcyI6Im1pbmltYXgifQ.I9BUm_chIzCjn_gDdVF1gJE7rpOvrD7D240lZT6dXyvq9sEYuYlXmnXZANXNwkZAh4vQb5X8uw48bQ0ul5z0VtRPXSHoQURL-lfmOrTGKrz47ckGhazYJCR45OGCDcm_qyotLLRUNeHft0wvC4AZe4kWzYL5zPw3wOpXCcyTLR2wSYCu_sTzFpHHgKCUcPHPsSQfy9u2JRmX9Gf2NE0ZAowGZiZWBModWAUhwiTbAfXP0Hws9hJIJooZWy-J0W6vIfoljMaPfqoqYBUtQimmXMbzEo2X_itCKlrIkl5N_aZNFRqkjN6qcLxegxt96KPSnl6hRnSppBcZD9lVD0kzbg"
headers = {"Authorization": f"Bearer {api_key}"}

payload = {
    "model": "MiniMax-Hailuo-02",
    "prompt": "A man picks up a book [Pedestal up], then reads [Static shot].",
    "duration": 6,
    "resolution": "1080P",
}

response = requests.post(url, headers=headers, json=payload)
response.raise_for_status()
print(response.json())
