token = "mytoken"

pg_credentials = {
  "host": "localhost",
  "port": 5432,
  "user": "myuser",
  "database": "mydb",
  "password": "mypassword",
  "timeout": 60
}

bot_log = 1234567890  # replace this with the ID of your bot logging channel
 
admins = [1234567890, 9876543210]  # add IDs of anyone who needs admin perms on this bot

authority_roles = [1234567890, 9876543210]  # IDs of roles that have authority over this bot (Blob Police, etc)

council_roles = [1234567890, 9876543210]  # IDs of roles considered Council (Blob Council, Blob Council Lite, etc)

blob_guilds = [37428175841, ]  # IDs of all guilds the bot updates an emoji list in

approve_emoji_id = 1234567890  # ID of the approval emoji
deny_emoji_id = 1234567890  # ID of the denial emoji

approve_emoji = "name:1234567890"  # representation of the approval emoji
deny_emoji = "name:1234567890"  # representation of the denial emoji

suggestions_channel = 1234567890  # ID of the suggestions channel
council_queue = 1234567890  # ID of the council queue channel
approval_queue = 1234567890  # ID of the approval queue channel

suggestions_log = 1234567890  # ID of the suggestions log channel
council_changelog = 1234567890  # ID of the council changelog channel
  
required_difference = 15 # The difference between upvotes and downvotes required to approve/deny automatically
required_votes = 15 # The amount of votes needed to process the votes