"""Token usage tracking tool."""

from nanobot.agent.tools.base import Tool


class TokensTool(Tool):
    """Tool to show token usage statistics."""
    
    name = "tokens"
    description = "Show token usage statistics for today or a period."
    
    parameters = {
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "description": "Period to show: 'today' (default), 'week', or 'month'",
                "enum": ["today", "week", "month"],
            },
        },
        "required": [],
    }
    
    async def execute(self, period: str = "today") -> str:
        """Execute the tokens tool."""
        try:
            from nanobot.memory import get_token_usage_today, get_token_usage_period
            
            if period == "today":
                stats = get_token_usage_today()
                
                if stats["total_tokens"] == 0:
                    return "📊 Сегодня токены ещё не использовались."
                
                lines = [
                    f"📊 **Токены за {stats['date']}**",
                    "",
                    f"📥 Prompt: **{stats['prompt_tokens']:,}**",
                    f"📤 Completion: **{stats['completion_tokens']:,}**",
                    f"📦 Всего: **{stats['total_tokens']:,}**",
                    f"🔄 Запросов: **{stats['requests']}**",
                ]
                
                if stats["by_model"]:
                    lines.append("")
                    lines.append("**По моделям:**")
                    for m in stats["by_model"]:
                        lines.append(f"  • {m['model']}: {m['total_tokens']:,} ({m['requests']} req)")
                
                return "\n".join(lines)
            
            elif period == "week":
                days = get_token_usage_period(7)
                
                if not days:
                    return "📊 Нет данных за последнюю неделю."
                
                total = sum(d["total_tokens"] for d in days)
                total_requests = sum(d["requests"] for d in days)
                
                lines = [
                    "📊 **Токены за неделю**",
                    "",
                    f"📦 Всего: **{total:,}**",
                    f"🔄 Запросов: **{total_requests}**",
                    "",
                    "**По дням:**",
                ]
                
                for d in days:
                    lines.append(f"  • {d['date']}: {d['total_tokens']:,} ({d['requests']} req)")
                
                return "\n".join(lines)
            
            elif period == "month":
                days = get_token_usage_period(30)
                
                if not days:
                    return "📊 Нет данных за последний месяц."
                
                total = sum(d["total_tokens"] for d in days)
                total_requests = sum(d["requests"] for d in days)
                
                lines = [
                    "📊 **Токены за месяц**",
                    "",
                    f"📦 Всего: **{total:,}**",
                    f"🔄 Запросов: **{total_requests}**",
                    f"📅 Дней с активностью: **{len(days)}**",
                    f"📈 Среднее в день: **{total // len(days) if days else 0:,}**",
                ]
                
                return "\n".join(lines)
            
            else:
                return f"❌ Неизвестный период: {period}. Используй: today, week, month"
                
        except Exception as e:
            return f"❌ Ошибка получения статистики: {e}"
