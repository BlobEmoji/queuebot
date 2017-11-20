# -*- coding: utf-8 -*-

# strings taken from https://github.com/b1naryth1ef

__all__ = ('BOT_BROKEN_MSG', 'BAD_SUGGESTION_MSG', 'SUGGESTION_RECIEVED', 'SUGGESTION_APPROVED', 'SUGGESTION_DENIED')


BAD_SUGGESTION_MSG = (
    'Heya! Looks like you tried to suggest '
    'an emoji to the Blob Server. Unfortunately it looks like '
    'you didn\'t send your message in the right format, so I wasn\'t able '
    'to understand it. To suggest an emoji, you must post the emoji name, '
    'like so: `:my_emoji_name:` and upload the emoji as an attachment. Feel '
    'free to try again, and if you are still having problems ask in <#289482554250100736>'
)

SUGGESTION_RECIEVED = (
    'Thanks for your emoji submission to the '
    'Google Blob Server! It\'s been added to our internal vote queue, '
    'so expect an update soon!'
)

SUGGESTION_APPROVED = (
    'Looks like one of your emoji suggestions was '
    'passed through our internal queue! Check out <#298920394751082507> to see '
    'which it was and go vote for you suggestion in <#289847856033169409>!'
)

SUGGESTION_DENIED = (
    'Unfortunately, your emoji suggestion was denied after going '
    'through internal review. Check out <#298920394751082507> to see\ '
    'which it was. Feel free to keep suggesting more emoji, but please '
    'don\'t submit the same one unless you\'ve modified it significantly!'
)

# hope this never happens :3
BOT_BROKEN_MSG = (
    'Looks like QueueBot is currently having some technical difficulties. '
    'The Blob Police have been informed and this problem will be fixed.'
)
