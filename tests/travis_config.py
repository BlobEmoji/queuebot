token = ""

pg_credentials = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "database": "travis_testdb",
    "timeout": 60
}

bot_log = 123456789012345678  # replace this with the ID of your bot logging channel

admins = [234567890123456789, 345678901234567890]  # add IDs of anyone who needs admin perms on this bot

authority_roles = [456789012345678901,
                   567890123456789012]  # IDs of roles that have authority over this bot (Blob Police, etc)

council_roles = [678901234567890123,
                 789012345678901234]  # IDs of roles considered Council (Blob Council, Blob Council Lite, etc)

blob_guilds = [890123456789012345]  # IDs of all guilds the bot updates an emoji list in

approve_emoji_id = 901234567890123456  # ID of the approval emoji
deny_emoji_id = 876543210987654321  # ID of the denial emoji

approve_emoji = "ok:901234567890123456"  # representation of the approval emoji
deny_emoji = "notok:876543210987654321"  # representation of the denial emoji

suggestions_channel = 987654321098765432  # ID of the suggestions channel
council_queue = 98765432109876543  # ID of the council queue channel
approval_queue = 109876543210987654  # ID of the approval queue channel

suggestions_log = 210987654321098765  # ID of the suggestions log channel
council_changelog = 321098765432109876  # ID of the council changelog channel

required_difference = 5  # The majority required to reach a conclusive council vote.
required_votes = 15  # The minimum amount of votes required to make a conclusive council vote.
