import datetime
import pprint
import os
import re

from dotenv import load_dotenv
import praw
import requests

load_dotenv()

DISCORD_USER_ID = "128739147115397120"

try:
    from redis import Redis
    client = Redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True)
except (ImportError, ValueError):
    Redis = None
    client = {"freegamedealsdiscord:last_checked": 0}


# ===============================================================================
# HELPER FUNCTIONS
# ===============================================================================


def post_to_discord(webhook_url, game_deals):
    """
    Posts the game deal to the webhook
    """
    for title, url in game_deals:
        print(f"\tPosting \"{' '.join(title.split())}\" to {webhook_url}")
        discord_mention = f"<@{DISCORD_USER_ID}>" if "postmates" in url else ""
        requests.post(
            webhook_url,
            json={
                "content": f"{title}\n{discord_mention}\n{url}"
            }
        )


def valid_deal(subreddit, submission):
    if subreddit == "gamedeals":
        title = submission.title.lower()
        for deal in re.findall(r'\(([^)]+)\)', title):
            return (
                # Indicate that it's a free game
                ("free" in deal or "100% off" in deal or "-100%" in deal) and
                # Indicates that the game hasn't expired
                submission.link_flair_text != "Expired" and
                # Indicates that the deal isn't a sale promotion
                not "sale" in title and
                # Indicates that the deal is an indie game
                not ("itch.io" in title or "indiegala" in title)
            )
    elif subreddit == "gamedealsfree":
        return submission.author in ["GameDealsBot1", "GameDealsBot2"]
    return False


def fetch_game_deals(subreddit, last_checked):
    """
    Fetches game deals from r/{subreddit} and cycle through to determine
    which deals to post.
    """
    print("=== Fetching Game Deals ===")
    reddit = praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID"),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
        user_agent="SothearoSB's Discord Notifier"
    )

    results = []
    submissions = reddit.subreddit(subreddit).new()
    while submissions:
        last_utc = 0
        for submission in submissions:
            if submission.created_utc < last_checked:
                submissions = None
                print("\tOld thread found!")
                print("\tThread posted date:", submission.created_utc)
                print("\tLast checked:", last_checked)
                break
            
            # Update the last utc for fetching the next page
            last_utc = submission.created_utc

            print("\tAnalyzing", submission.title)
            if valid_deal(subreddit, submission):
                title = submission.title
                url = submission.url

                # If it's a crosspost, then we fetch the url of the post
                if not submission.is_original_content:
                    original_submission = reddit.submission(url=submission.url)
                    if original_submission.spoiler:
                        # If the original submission is a spoiler
                        # Then the deal has expired and we should move on
                        print("\t\tOriginal thread has expired... skipping")
                        continue
                    else:
                        url = original_submission.url

                print("\t\tValid")
                results.append((title, url))
            else:
                print("\t\tInvalid")

        if submissions:
            submissions = reddit.subreddit(subreddit).new(params={"after": last_utc})

    print(len(results), "results found!")
    if results:
        pprint.pp(results)
    return results


def fetch_postmates_codes(subreddit, last_checked):
    if not subreddit:
        subreddit = "postmates"

    print("=== Fetching Postmates Codes ===")
    reddit = praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID"),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
        user_agent="SothearoSB's Discord Notifier"
    )
    submission: praw.models.Submission = reddit.subreddit(subreddit).sticky()
    submission.comment_sort = "new"
    comments: praw.models.comment_forest.CommentForest = submission.comments
    comments.replace_more(limit=0)

    result = []
    for comment in comments.list():
        if comment.created_utc < last_checked:
            print("\tOld comment found!")
            print("\tComment posted date:", comment.created_utc)
            print("\tLast checked:", last_checked)
            break

        if "austin" in comment.body.lower():
            result.append(("Postmates Monthly Promo Codes: " + comment.body, "https://reddit.com" + comment.permalink))

    print(len(result), "results found!")
    if result:
        pprint.pp(result)
    return result


# ===============================================================================
# MAIN
# ===============================================================================


def main():
    print("=== Getting last_checked ===")
    last_checked = 0
    if os.path.exists("last_checked.txt"):
        with open("last_checked.txt") as f:
            last_checked = float(f.readline())
    else:
        last_checked = float(client.get("freegamedealsdiscord:last_checked"))
    new_last_checked = datetime.datetime.utcnow().timestamp() // 1  # Floor Division

    print("\tlast_checked:", last_checked)
    print("\tnew_last_checked:", new_last_checked)

    # Fetch the free game deals and post to the discord webhooks
    postmate_codes = fetch_postmates_codes("postmates", last_checked)
    game_deals = fetch_game_deals("gamedealsfree", last_checked)
    post_to_discord(os.environ.get("VISA_DISCORD_WEBHOOK"), postmate_codes + game_deals)
    post_to_discord(os.environ.get("OSNN_DISCORD_WEBHOOK"), game_deals)

    # Set the new time after execution is done
    with open("last_checked.txt", "w") as f:
        f.write(str(new_last_checked))


if __name__ == "__main__":
    main()
