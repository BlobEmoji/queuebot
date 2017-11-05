CREATE TABLE IF NOT EXISTS suggestions (
    -- suggestion id
    idx SERIAL PRIMARY KEY,

    -- user that submitted the emoji
    user_id BIGINT,

    -- message id in the #council-queue
    council_message_id BIGINT,

    -- message id in the #approval-queue
    public_message_id BIGINT,

    -- emoji data
    emoji_id BIGINT,
    emoji_name TEXT,

    -- votes
    upvotes INT DEFAULT 0,
    downvotes INT DEFAULT 0
);
