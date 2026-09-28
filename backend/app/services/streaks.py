from datetime import date, timedelta

def streak_metrics(activity_dates: set[date], today: date) -> tuple[int, int]:
    current = 0
    # A streak remains current through the day after its latest activity, giving
    # the user until local midnight to complete today's learning action.
    cursor = today if today in activity_dates else today - timedelta(days=1)
    while cursor in activity_dates:
        current += 1
        cursor -= timedelta(days=1)
    longest = 0
    run = 0
    previous = None
    for active in sorted(activity_dates):
        run = run + 1 if previous and active == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = active
    return current, longest
