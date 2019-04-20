
CREATE TABLE IF NOT EXISTS suggestions (
    -- suggestion id
    idx SERIAL PRIMARY KEY,

    -- user that submitted the emoji
    user_id BIGINT,

    -- message id in the #council-queue
    council_message_id BIGINT,

    -- message id in the #approval-queue
    public_message_id BIGINT,

    -- message id in the #suggestions
    suggestions_message_id BIGINT,

    -- emoji data
    emoji_id BIGINT,
    emoji_name TEXT,
    emoji_animated BOOLEAN,

    note TEXT,

    -- votes
    upvotes INT DEFAULT 0,
    downvotes INT DEFAULT 0,

    -- timestamps
    submission_time TIMESTAMP, -- when this was submitted
    validation_time TIMESTAMP, -- when this was approved or denied

    -- validation
    council_approved BOOLEAN, -- was the emoji approved by Council?
    forced_reason TEXT, -- reason for Council validation being forced.
    forced_by BIGINT, -- ID of the user who forced this. if not forced, this is NULL.
    revoked BOOLEAN -- emoji was revoked by submitter
);

CREATE TABLE IF NOT EXISTS council_votes (
    -- idx of the suggestion this vote is for
    suggestion_index INT REFERENCES suggestions ON DELETE CASCADE,

    -- user that made this vote
    user_id BIGINT,

    PRIMARY KEY (suggestion_index, user_id),

    -- has this user voted approve?
    has_approved BOOLEAN DEFAULT FALSE,

    -- has this user voted deny?
    has_denied BOOLEAN DEFAULT FALSE,

    -- time when this vote was made
    vote_time TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);
