import random
import logging
from logging import getLogger

from pyrogram import filters
from pyrogram.types import Message
from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.helper import use_chat_lang
from tiensiteo.vars import COMMAND_HANDLER
from database.funny_db import can_use_command, update_user_command_usage

# Định nghĩa các câu đạo lý
DAO_LY_LIST = [
    "Đời là bể khổ, qua được bể khổ là qua đời.",
    "Tiền không mua được tất cả, nhưng tất cả đều cần tiền.",
    "Đừng bao giờ từ bỏ ước mơ, hãy ngủ thêm một chút.",
    "Thành công không phải là chìa khóa của hạnh phúc, hạnh phúc mới là chìa khóa của thành công.",
    "Con đường ngàn dặm bắt đầu từ một bước chân. Con đường nghìn bước chân bắt đầu từ một cú vấp ngã.",
    "Nếu bạn không xây dựng ước mơ của mình, người khác sẽ thuê bạn để xây dựng ước mơ của họ.",
    "Bạn không thể thay đổi hướng gió, nhưng bạn có thể điều chỉnh cánh buồm của mình.",
    "Cuộc sống giống như một chiếc xe đạp. Để giữ thăng bằng, bạn phải tiếp tục di chuyển.",
    "Người ta chỉ sống một lần, nhưng nếu sống đúng, một lần là đủ.",
    "Cách tốt nhất để dự đoán tương lai là tạo ra nó.",

    # Các câu hài hước & cà khịa
    "Cuộc sống giống như Wi-Fi, bạn cứ đi tìm tín hiệu mà không biết nó ở đâu.",
    "Tôi không lười, tôi chỉ đang ở chế độ tiết kiệm năng lượng thôi.",
    "Tiền không mua được hạnh phúc, nhưng nó có thể mua được một chiếc du thuyền để bạn đến gần hơn với hạnh phúc.",
    "Tôi không có gì để mất... trừ đi cái bụng béo và vài năm tuổi thọ.",
    "Sống ảo không xấu, xấu là khi bạn quên mất mình đang sống thật.",
    "Thứ duy nhất dễ dàng vào buổi sáng là quay trở lại giấc ngủ.",
    "Nếu bạn nghĩ rằng không ai quan tâm đến bạn, hãy thử bỏ lỡ một vài hóa đơn.",
    "Tôi không béo, tôi chỉ có nhiều không gian để yêu thương thôi.",
    "Bạn không thể làm hài lòng tất cả mọi người, bạn không phải là pizza.",
    "Tôi không nói dối, tôi chỉ kể chuyện theo một cách sáng tạo hơn thôi.",
    "Cách tốt nhất để thoát khỏi cám dỗ là nhượng bộ nó.",
    "Tôi không procrastinate, tôi chỉ chờ đợi cảm hứng đến thôi.",
    "Tôi đã cố gắng giảm cân. Nhưng rồi tôi nhận ra tôi yêu đồ ăn hơn là yêu cơ thể mình.",
    "Tôi không cần một nhà trị liệu, tôi chỉ cần một chiếc Wi-Fi tốt và một tách cà phê.",
    "Tôi không bao giờ trì hoãn việc gì quan trọng. Trừ khi nó liên quan đến việc dọn dẹp nhà cửa.",
    "Hạnh phúc là khi bạn không cần phải giả vờ là ai đó khác.",
    "Nếu cuộc sống cho bạn chanh, hãy làm nước chanh. Nếu cuộc sống cho bạn một cục đá, hãy phàn nàn về nó trên mạng xã hội.",
    "Thành công là một hành trình, không phải là đích đến. Và trên hành trình đó, bạn sẽ gặp rất nhiều chướng ngại vật gọi là 'deadline'.",
    "Đừng bao giờ từ bỏ ước mơ của mình. Ngủ thêm 5 phút đi, biết đâu bạn sẽ mơ tiếp được.",
    "Tôi không phải là một lập trình viên giỏi, tôi chỉ là một người tìm kiếm Google tốt.",
    "Cuộc đời là một trò chơi, và tôi đang chơi ở chế độ khó.",
    "Tôi tin vào việc giữ gìn sức khỏe. Bằng cách nào? Bằng cách tránh xa những người khiến tôi đau đầu.",
    "Nếu bạn đang đọc cái này, thì bạn đang lãng phí thời gian. Trừ khi bạn đang đọc để tìm cảm hứng.",
    "Đừng bao giờ hứa hẹn những điều bạn không thể thực hiện. Trừ khi bạn đang hứa với chính mình là sẽ đi tập gym vào ngày mai.",
    "Nụ cười là liều thuốc tốt nhất. Trừ khi bạn bị đau răng.",
    "Tiền không phải là tất cả, nhưng nó có thể mua được một chiếc vé hạng nhất để đến những nơi có tất cả.",
    "Tôi luôn cố gắng học hỏi từ những sai lầm của người khác. Đó là lý do tại sao tôi luôn có rất nhiều người để học hỏi.",
    "Thời gian là vàng bạc. Vậy nên tôi đang lãng phí vàng bạc để viết những dòng này.",
    "Hãy là chính mình. Trừ khi bạn có thể là Batman, thì hãy là Batman.",
    "Cuộc đời giống như một hộp sô cô la, bạn không bao giờ biết mình sẽ nhận được gì. Tôi hy vọng không phải là sô cô la đắng.",
    "Sự thật sẽ giải phóng bạn. Nhưng trước tiên nó sẽ làm bạn nổi điên.",
    "Cuộc sống là một trò đùa, và chúng ta là những diễn viên phụ.",
    "Hôm nay là ngày tốt để bắt đầu một điều gì đó mới... như ăn thêm một bữa nữa chẳng hạn.",
    "Cuộc sống thật ngắn ngủi, đừng phí phạm nó vào việc làm những điều bạn không thích. Hãy dành nó để ngủ nướng!",
    "Tôi không phải là một người hoàn hảo, nhưng tôi đang cố gắng để trở thành một người hoàn hảo hơn mỗi ngày... hoặc ít nhất là không tệ hơn.",
    "Nếu bạn muốn thành công, hãy nhân đôi tỷ lệ thất bại của bạn.",
    "Đừng nói với tôi rằng bầu trời là giới hạn khi có dấu chân trên Mặt trăng.",
    "Tôi không thể hứa với bạn một tương lai không có rắc rối, nhưng tôi có thể hứa với bạn một tương lai có Wi-Fi miễn phí.",
    "Tôi không lười, tôi chỉ đang bảo tồn năng lượng vũ trụ.",
    "Nếu bạn không thích điều gì đó, hãy thay đổi nó. Nếu bạn không thể thay đổi nó, hãy thay đổi thái độ của bạn.",
    "Cuộc đời là một cuốn sách, và những kẻ không du lịch chỉ đọc được một trang.",
    "Thành công là kết quả của sự chuẩn bị, làm việc chăm chỉ và học hỏi từ thất bại. Hoặc đơn giản là may mắn.",

    # Các câu về cuộc sống & triết lý
    "Từng ngày là một cơ hội để thay đổi tương lai.",
    "Cách duy nhất để làm một công việc tuyệt vời là yêu những gì bạn làm.",
    "Cách tốt nhất để dự đoán tương lai là tạo ra nó.",
    "Nếu bạn muốn có một cuộc sống hạnh phúc, hãy cột nó vào một mục tiêu, chứ không phải vào con người hay đồ vật.",
    "Cuộc sống là một cuộc phiêu lưu táo bạo hoặc không là gì cả.",
    "Đừng chạy theo số đông, hãy tự tạo ra con đường của riêng bạn.",
    "Hạnh phúc không phải là một đích đến, mà là một hành trình.",
    "Hãy sống trọn vẹn từng khoảnh khắc, vì mỗi khoảnh khắc đều là duy nhất.",
    "Mọi thứ đều có vẻ không thể cho đến khi nó được thực hiện.",
    "Đừng đếm những gì bạn đã mất, hãy trân trọng những gì bạn đang có và làm việc để có được những gì bạn muốn.",
    "Thử thách biến cuộc sống trở nên thú vị, và vượt qua chúng làm cuộc sống có ý nghĩa.",
    "Sự thay đổi là quy luật của cuộc sống. Những người chỉ nhìn vào quá khứ hoặc hiện tại chắc chắn sẽ bỏ lỡ tương lai.",
    "Sự kiên nhẫn là chìa khóa của mọi thứ.",
    "Hãy sống một cuộc đời mà bạn muốn kể lại.",
    "Cuộc sống không phải là việc chờ đợi cơn bão qua đi, mà là học cách nhảy múa dưới mưa.",
    "Điều vĩ đại nhất bạn có thể học là yêu và được yêu lại.",
    "Mỗi ngày không phải là một khởi đầu mới, mà là một cơ hội mới.",
    "Không bao giờ là quá muộn để trở thành người mà bạn muốn trở thành.",
    "Bạn là người duy nhất chịu trách nhiệm cho hạnh phúc của chính mình.",
    "Cố gắng không phải là thất bại. Không cố gắng mới là thất bại thực sự.",
    "Đừng sợ hãi sự hoàn hảo, bạn sẽ không bao giờ đạt được nó đâu.",
    "Những người vĩ đại không bao giờ ngừng học hỏi.",
    "Không có con đường tắt đến bất cứ nơi nào đáng để đi.",
    "Bạn mạnh mẽ hơn bạn nghĩ, và có thể làm được nhiều hơn bạn tưởng.",
    "Khi bạn thay đổi cách bạn nhìn mọi thứ, những thứ bạn nhìn sẽ thay đổi.",
    "Cuộc sống là 10% những gì xảy ra với bạn và 90% cách bạn phản ứng với nó.",
    "Đừng để ngày hôm qua chiếm quá nhiều của ngày hôm nay.",
    "Chỉ có một cách để tránh phê phán: không làm gì, không nói gì, và không là gì cả.",
    "Mục đích của cuộc đời là tìm thấy mục đích của mình và cho đi nó.",
    "Tương lai thuộc về những người tin vào vẻ đẹp của những giấc mơ của họ.",
    "Hãy làm những gì bạn có thể, với những gì bạn có, ở nơi bạn đang ở.",
    "Nếu bạn không mạo hiểm, bạn sẽ không bao giờ đạt được điều gì.",
    "Sống không phải để tồn tại, mà là để vươn tới, để chinh phục.",
    "Mỗi ngày là một trang trắng. Hãy viết một câu chuyện tuyệt vời.",
    "Sự thật là ánh sáng dẫn lối cho chúng ta.",
    "Hãy tìm kiếm vẻ đẹp trong mọi thứ, và bạn sẽ tìm thấy hạnh phúc.",
    "Trưởng thành là khi bạn học cách chấp nhận những điều bạn không thể thay đổi.",
    "Những người thực sự thành công là những người luôn sẵn sàng giúp đỡ người khác.",
    "Đừng chờ đợi cơ hội. Hãy tạo ra chúng.",
    "Sự đơn giản là chìa khóa của sự vĩ đại.",
    "Giá trị của một người nằm ở những gì họ cho đi, không phải ở những gì họ nhận được.",
    "Hãy sống một cuộc đời mà khi bạn ra đi, thế giới sẽ nhớ về bạn.",
    "Những điều tốt đẹp đến với những ai chờ đợi, nhưng những điều tốt hơn đến với những ai ra ngoài và tìm kiếm chúng.",
    "Thành công là tổng hợp của những nỗ lực nhỏ lặp đi lặp lại hàng ngày.",
    "Hãy biến ước mơ của bạn thành kế hoạch và thực hiện nó.",
    "Cuộc sống là một món quà. Đừng lãng phí nó.",
    "Hành động nhỏ, kết quả lớn.",
    "Tìm thấy niềm vui trong những điều nhỏ nhặt nhất.",
    "Đừng bao giờ hối tiếc về những gì đã làm, chỉ hối tiếc về những gì đã không làm.",
    "Con người được tạo ra để yêu, vật chất được tạo ra để sử dụng. Lý do thế giới hỗn loạn là vì vật chất được yêu và con người được sử dụng.",

    # Các câu về tình yêu & quan hệ
    "Tình yêu không phải là nhìn nhau, mà là cùng nhìn về một hướng.",
    "Yêu là khi bạn không cần phải nói một lời nào, nhưng người đó vẫn hiểu.",
    "Tình yêu là một động từ. Yêu là sự cho đi vô điều kiện.",
    "Hạnh phúc trong hôn nhân không phải là tìm được một người phù hợp, mà là trở thành một người phù hợp.",
    "Tình yêu đích thực không phải là về sự hoàn hảo, mà là về sự chấp nhận những khuyết điểm của nhau.",
    "Bạn biết mình yêu ai đó khi bạn muốn họ hạnh phúc hơn chính mình, ngay cả khi hạnh phúc đó không bao gồm bạn.",
    "Mối quan hệ tốt đẹp không phải là thứ tự nhiên có, mà là thứ được xây dựng hàng ngày.",
    "Tình bạn là một linh hồn sống trong hai cơ thể.",
    "Yêu thương là không bao giờ phải nói lời xin lỗi.",
    "Tình yêu không cần lý do, nó chỉ đơn giản là vậy.",
    "Yêu thương không phải là việc sở hữu, mà là việc cho đi.",
    "Đừng yêu ai đó vì vẻ bề ngoài của họ, hãy yêu họ vì trái tim họ.",
    "Sự tin tưởng là nền tảng của mọi mối quan hệ.",
    "Hãy yêu thương như thể bạn chưa bao giờ bị tổn thương.",
    "Càng cho đi yêu thương, bạn càng nhận lại được nhiều hơn.",

    # Các câu về công việc & học tập
    "Làm việc thông minh, không phải làm việc chăm chỉ.",
    "Đầu tư vào kiến thức luôn mang lại lợi nhuận tốt nhất.",
    "Học tập là ánh sáng cho cuộc đời.",
    "Sai lầm là bằng chứng cho thấy bạn đang cố gắng.",
    "Đừng chỉ đọc sách, hãy sống những gì bạn đọc.",
    "Mỗi lỗi lầm là một bài học, không phải là một thất bại.",
    "Chất lượng hơn số lượng.",
    "Không có gì là không thể với một trái tim sẵn sàng và một bộ não không ngừng học hỏi.",
    "Tạo ra một cuộc sống mà bạn không cần phải trốn tránh khỏi nó.",
    "Học tập là một kho báu sẽ theo bạn mọi nơi.",
    "Kiến thức là sức mạnh.",
    "Sự chăm chỉ là mẹ của may mắn.",
    "Sự cống hiến không ngừng dẫn đến sự thành công không ngừng.",

    # Các câu về suy ngẫm & động lực
    "Hãy là phiên bản tốt nhất của chính bạn, không phải là bản sao của người khác.",
    "Sức mạnh của bạn không nằm ở cơ bắp, mà ở tinh thần.",
    "Không có gì có thể dập tắt ánh sáng từ bên trong bạn.",
    "Hãy tin vào chính mình, bạn mạnh mẽ hơn bạn tưởng.",
    "Cuộc đời là một hành trình tự khám phá.",
    "Sự tự tin là trang phục đẹp nhất mà bạn có thể mặc.",
    "Mỗi ngày là một cơ hội để bắt đầu lại.",
    "Đừng ngại thay đổi. Nó có thể là điều tốt nhất từng xảy ra với bạn.",
    "Hãy biết ơn những gì bạn có, và bạn sẽ có nhiều hơn.",
    "Tư duy tích cực tạo nên cuộc sống tích cực.",
    "Hãy trân trọng những khoảnh khắc hiện tại.",
    "Sự thật là ánh sáng dẫn lối cho chúng ta.",
    "Hãy tìm kiếm vẻ đẹp trong mọi thứ, và bạn sẽ tìm thấy hạnh phúc.",
    "Trưởng thành là khi bạn học cách chấp nhận những điều bạn không thể thay đổi.",
    "Những người thực sự thành công là những người luôn sẵn sàng giúp đỡ người khác.",
    "Đừng chờ đợi cơ hội. Hãy tạo ra chúng.",
    "Sự đơn giản là chìa khóa của sự vĩ đại.",
    "Giá trị của một người nằm ở những gì họ cho đi, không phải ở những gì họ nhận được.",
    "Hãy sống một cuộc đời mà khi bạn ra đi, thế giới sẽ nhớ về bạn.",
    "Những điều tốt đẹp đến với những ai chờ đợi, nhưng những điều tốt hơn đến với những ai ra ngoài và tìm kiếm chúng.",
    "Thành công là tổng hợp của những nỗ lực nhỏ lặp đi lặp lại hàng ngày.",
    "Hãy biến ước mơ của bạn thành kế hoạch và thực hiện nó.",
    "Cuộc sống là một món quà. Đừng lãng phí nó.",
    "Tìm thấy niềm vui trong những điều nhỏ nhặt nhất.",
    "Đừng bao giờ hối tiếc về những gì đã làm, chỉ hối tiếc về những gì đã không làm.",
    "Bạn không thể kiểm soát tất cả mọi thứ, nhưng bạn có thể kiểm soát cách bạn phản ứng với chúng.",
    "Điều quan trọng không phải là bạn ngã bao nhiêu lần, mà là bạn đứng dậy bao nhiêu lần.",
    "Hạnh phúc không phải là một sự kiện, nó là một lựa chọn.",
    "Hãy trân trọng những người bạn yêu thương và nói với họ điều đó.",
    "Cuộc sống là sự cân bằng giữa việc nắm giữ và buông bỏ.",
    "Hãy là ngọn đèn của chính bạn.",
    "Mọi thứ đều có thể nếu bạn tin tưởng.",
    "Đừng sợ thất bại, hãy sợ không cố gắng.",
    "Sự tử tế là một ngôn ngữ mà người điếc có thể nghe và người mù có thể thấy.",
    "Hãy sống một cuộc đời đầy ý nghĩa.",
    "Không có gì là ngẫu nhiên, mọi thứ đều có lý do.",
    "Sự bình yên đến từ bên trong. Đừng tìm kiếm nó bên ngoài.",
    "Hãy hít thở sâu và tin tưởng vào bản thân.",
    
    # Một số câu chế thêm
    "Tình yêu sét đánh là có thật, nhưng tình bạn sét đánh trúng đầu thì lại càng đáng sợ hơn.",
    "Đừng bao giờ tranh cãi với kẻ ngốc, họ sẽ kéo bạn xuống trình độ của họ và đánh bại bạn bằng kinh nghiệm.",
    "Hạnh phúc là khi bạn tìm thấy chiếc tất còn lại sau khi giặt.",
    "Cuộc sống không phải là vấn đề cần giải quyết, mà là một thực tế cần trải nghiệm... đặc biệt là khi có đồ ăn ngon.",
    "Tôi không già đi, tôi chỉ thăng cấp thôi.",
    "Nếu bạn thấy mình đang đi trên con đường bằng phẳng, hãy kiểm tra lại, có lẽ bạn đang đi sai đường.",
    "Sự thật có thể đau lòng, nhưng nó ít đau hơn lời nói dối lặp đi lặp lại.",
    "Sự khác biệt giữa một ngày tồi tệ và một cuộc sống tồi tệ là thái độ của bạn.",
    "Đừng mơ về thành công, hãy thức dậy và làm việc chăm chỉ để biến nó thành hiện thực.",
    "Sự im lặng không phải là khoảng trống, nó là câu trả lời.",
    "Đôi khi, điều tốt nhất bạn có thể làm là không làm gì cả."
]

# Khởi tạo logger cho module này
LOGGER = getLogger("TienSiTeo")

__MODULE__ = "DaoLy"
__HELP__ = "<blockquote>/daoly - Gửi một câu đạo lý ngẫu nhiên. (Chỉ dùng được 1 lần/ngày)</blockquote>"

@app.on_message(filters.command(["daoly"], COMMAND_HANDLER))
@capture_err
@use_chat_lang()
async def daoly(_, ctx: Message, strings):
    """
    Gửi một câu đạo lý ngẫu nhiên được bọc trong thẻ blockquote,
    có giới hạn sử dụng 1 lần/ngày cho mỗi người dùng,
    và nhắc đến người dùng trong câu trả lời.
    """
    # Gửi một tin nhắn tạm thời để thông báo đang xử lý
    msg = await ctx.reply_msg("Đang xử lý đạo lý...", quote=True)

    try:
        # Kiểm tra xem tin nhắn có phải từ người dùng hợp lệ không
        if not ctx.from_user:
            await msg.edit_msg("Lệnh này chỉ dành cho người dùng, không phải kênh hoặc nhóm ẩn danh!")
            return

        # Lấy ID người gửi và ID chat
        sender_id = ctx.from_user.id
        sender_mention = ctx.from_user.mention(style="markdown") # Lấy mention của người gửi
        chat_id = ctx.chat.id
        command = "daoly" # Tên lệnh để theo dõi việc sử dụng trong cơ sở dữ liệu

        # Kiểm tra xem người dùng có được phép sử dụng lệnh hôm nay không
        if not await can_use_command(chat_id, sender_id, command):
            await msg.edit_msg(
                f"🚫 Bạn đã sử dụng lệnh /{command} hôm nay. Hãy thử lại vào ngày mai! 😊"
            )
            return

        # Nếu người dùng được phép, tiến hành lấy và gửi câu đạo lý
        random_daoly = random.choice(DAO_LY_LIST)
        
        # Tạo chuỗi HTML với dòng nhắc đến người dùng, blockquote và chữ ký
        response_text = (
            f"<b>Đây là đạo lý hôm nay dành cho {sender_mention}!</b>\n\n" # Dòng mới được thêm
            f"<blockquote>{random_daoly}</blockquote>\n\n"
            f"<i>Đạo lý bởi Tiến sĩ Tèo</i>"
        )
        
        # Gửi tin nhắn HTML
        await ctx.reply_msg(response_text, quote=True)
        
        # Cập nhật trạng thái sử dụng lệnh của người dùng trong cơ sở dữ liệu
        await update_user_command_usage(chat_id, sender_id, command)
        
        # Xóa tin nhắn tạm thời "Đang xử lý..." sau khi gửi thành công
        await msg.delete()

    except Exception as e:
        # Ghi log lỗi nếu có vấn đề xảy ra
        LOGGER.error(f"Lỗi trong lệnh daoly: {str(e)}")
        # Cập nhật tin nhắn lỗi cho người dùng
        await msg.edit_msg("Lỗi, vui lòng thử lại sau! 😔")

