from leetscrape import GetQuestion

q = GetQuestion(titleSlug="two-sum").scrape()
print(q.title, q.difficulty)
