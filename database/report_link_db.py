from database import dbname

report_link_db = dbname["report_links"]

# Kiểm tra xem chức năng báo cáo link có được bật trong nhóm không
async def is_report_link_enabled(chat_id: int) -> bool:
    data = await report_link_db.find_one({"chat_id": chat_id})
    return bool(data and data.get("report_link_enabled", False))

# Bật/tắt chức năng báo cáo link
async def toggle_report_link(chat_id: int):
    data = await report_link_db.find_one({"chat_id": chat_id})
    if data and data.get("report_link_enabled", False):
        await report_link_db.update_one(
            {"chat_id": chat_id},
            {"$set": {"report_link_enabled": False}}
        )
        return False
    else:
        await report_link_db.update_one(
            {"chat_id": chat_id},
            {"$set": {"report_link_enabled": True}},
            upsert=True
        )
        return True

# Lưu danh sách link loại trừ (whitelist)
async def set_excluded_links(chat_id: int, links: list):
    await report_link_db.update_one(
        {"chat_id": chat_id},
        {"$set": {"excluded_links": links}},
        upsert=True
    )

# Lấy danh sách link loại trừ
async def get_excluded_links(chat_id: int) -> list:
    data = await report_link_db.find_one({"chat_id": chat_id})
    return data.get("excluded_links", []) if data else []