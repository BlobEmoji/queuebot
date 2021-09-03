from discord.ext import commands


def is_police():
    def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        return any(role.id in ctx.bot.authority_roles for role in ctx.author.roles)
    return commands.check(predicate)


def is_council():
    def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        return any(role.id in ctx.bot.council_roles for role in ctx.author.roles)
    return commands.check(predicate)


def is_maker_or_cooldown(rate, per, bucket_type=commands.BucketType.default):
    cd = commands.CooldownMapping.from_cooldown(rate, per, bucket_type)

    def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        if any(role.id in ctx.bot.council_roles for role in ctx.author.roles):
            # is council
            return True
        
        if any(role.id in ctx.bot.maker_roles for role in ctx.author.roles):
            # is maker
            return True

        bucket = cd.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()

        if retry_after:
            raise commands.CommandOnCooldown(bucket, retry_after, cd.type)
        else:
            return True

    return commands.check(predicate)
