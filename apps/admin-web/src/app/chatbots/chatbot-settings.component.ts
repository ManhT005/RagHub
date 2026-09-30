import { ChangeDetectionStrategy, Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
@Component({selector:'raghub-chatbot-settings',imports:[FormsModule,RouterLink],templateUrl:'./chatbot-settings.component.html',styleUrl:'./chatbot-settings.component.css',changeDetection:ChangeDetectionStrategy.OnPush})
export class ChatbotSettingsComponent { name='Hỗ trợ sinh viên'; description='Chatbot hỗ trợ tư vấn thông tin tuyển sinh, chương trình đào tạo và học phí.'; published=true; readonly embed='<script src="https://raghub.vn/embed.js" data-chatbot="chat_123"></script>'; async copy(){ await navigator.clipboard?.writeText(this.embed); } }
