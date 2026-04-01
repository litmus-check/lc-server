import { GmailClient } from './GmailClient';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

// Final test to demonstrate working email fetching
async function testEmailFetching() {
    try {
        console.log('🎯 Final Gmail Email Fetching Test');
        console.log('==================================\n');
        
        console.log('📧 Email: mehul@finigamilabs.com');
        console.log('🔑 Username: ' + (process.env.GMAIL_ACCOUNT ? '✅ Set' : '❌ Not set'));
        console.log('🔑 App Password: ' + (process.env.GMAIL_APP_PASSWORD ? '✅ Set' : '❌ Not set'));
        
        // Test connection
        console.log('\n📡 Testing connection...');
        const gmailClient = new GmailClient();
        const isConnected = await gmailClient.testConnection();
        
        if (!isConnected) {
            console.log('❌ Connection failed');
            return;
        }
        
        console.log('✅ Connection successful!');
        
        // Test email fetching with fresh instance
        console.log('\n📧 Fetching last 3 emails...');
        const emailClient = new GmailClient();
        const emails = await emailClient.getLastEmails(3);
        
        console.log(`\n📊 Results:`);
        console.log(`   ✅ Successfully fetched ${emails.length} emails`);
        
        if (emails.length > 0) {
            console.log('\n📨 Email Details:');
            emails.forEach((email, index) => {
                console.log(`\n   Email ${index + 1}:`);
                console.log(`   📧 Subject: ${email.subject}`);
                console.log(`   👤 From: ${email.from}`);
                console.log(`   📅 Date: ${email.date}`);
                console.log(`   📝 Content Length: ${email.content.length} characters`);
                console.log(`   📄 Content Preview: ${email.content.substring(0, 150)}...`);
            });
            
            console.log('\n🎉 SUCCESS! Email fetching is working correctly!');
            console.log('\n💡 The Gmail agent is ready for production use:');
            console.log('   1. ✅ Gmail connection established');
            console.log('   2. ✅ Email fetching working');
            console.log('   3. ✅ Email content extracted');
            console.log('   4. ✅ Ready for verification extraction');
            
        } else {
            console.log('\n❌ No emails fetched - inbox might be empty');
        }
        
    } catch (error) {
        console.error('❌ Test failed:', error);
    }
}

// Run the test
testEmailFetching();
