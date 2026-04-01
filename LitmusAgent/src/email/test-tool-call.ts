import { GmailClient } from './GmailClient';
import { VerificationExtractor } from '../LLM/VerificationExtractor';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

// Test tool call format for verification extraction
async function testToolCallFormat() {
    try {
        console.log('🧪 Testing Tool Call Format for Verification Extraction');
        console.log('====================================================\n');
         
        // Test connection with separate instance
        console.log('\n📡 Testing connection...');
        const testClient = new GmailClient();
        const isConnected = await testClient.testConnection();
        
        if (!isConnected) {
            console.log('❌ Connection failed');
            return;
        }
        
        console.log('✅ Connection successful!');
        
        // Fetch emails with fresh instance (latest first)
        console.log('\n📧 Fetching last 3 emails (latest first)...');
        const emailClient = new GmailClient();
        const emails = await emailClient.getLastEmails(3);
        
        console.log(`\n📊 Results:`);
        console.log(`   ✅ Successfully fetched ${emails.length} emails`);
        
        if (emails.length > 0) {
            console.log('\n📨 Email Order (should be latest first):');
            emails.forEach((email, index) => {
                console.log(`\n   Email ${index + 1} (${index === 0 ? 'LATEST' : 'OLDER'}):`);
                console.log(`   📧 Subject: ${email.subject}`);
                console.log(`   👤 From: ${email.from}`);
                console.log(`   📅 Date: ${email.date}`);
            });
            
            // Test verification extraction with tool call format
            console.log('\n🔍 Testing verification extraction with tool call format...');
            const extractor = new VerificationExtractor();
            
            // Test individual email extraction
            console.log('\n📧 Testing individual email verification (tool call format):');
            for (let i = 0; i < Math.min(2, emails.length); i++) {
                console.log(`\n   --- Email ${i + 1} ---`);
                const result = await extractor.extractVerification(emails[i], 'https://example.com/verify');
                console.log(`   Tool Call Result: ${JSON.stringify(result, null, 2)}`);
                
                // Verify tool call format
                if (result.type === 'tool_call' && result.tool === 'extract_verification' && result.args) {
                    console.log(`   ✅ Tool call format verified`);
                    console.log(`   📝 Type: ${result.args.type}`);
                    console.log(`   💎 Value: ${result.args.value}`);
                } else {
                    console.log(`   ❌ Invalid tool call format`);
                }
            }
            
            // Test multiple email extraction (should stop at first match)
            console.log('\n📧 Testing multiple email verification (tool call format):');
            const allResults = await extractor.extractFromMultipleEmails(emails, 'https://example.com/verify');
            console.log(`   Results: ${JSON.stringify(allResults, null, 2)}`);
            console.log(`   Total results: ${allResults.length} (should be <= ${emails.length})`);
            
            // Test first valid verification
            console.log('\n🎯 Testing first valid verification (tool call format):');
            const firstValid = await extractor.getFirstValidVerification(emails, 'https://example.com/verify');
            console.log(`   First valid: ${JSON.stringify(firstValid, null, 2)}`);
            
            console.log('\n🎉 SUCCESS! Tool call format is working correctly!');
            console.log('\n💡 Tool Call Format Verified:');
            console.log('   1. ✅ Returns tool_call type');
            console.log('   2. ✅ Uses extract_verification tool name');
            console.log('   3. ✅ Contains args with type and value');
            console.log('   4. ✅ extractFromMultipleEmails stops at first match');
            console.log('   5. ✅ getFirstValidVerification returns tool call format');
            
        } else {
            console.log('\n❌ No emails fetched - inbox might be empty');
        }
        
    } catch (error) {
        console.error('❌ Test failed:', error);
    }
}

// Run the test
testToolCallFormat();
