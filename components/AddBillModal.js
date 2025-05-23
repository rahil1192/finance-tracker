import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Switch,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function AddBillModal({ navigation, route }) {
  const [activeTab, setActiveTab] = useState('BILLS');
  const [amount, setAmount] = useState('');
  const [title, setTitle] = useState('');
  const [autoPaid, setAutoPaid] = useState(false);
  const [addExpenseEntry, setAddExpenseEntry] = useState(true);
  const [notes, setNotes] = useState('');

  // Current date formatted as "Wed, 21 May 2025"
  const today = new Date();
  const options = { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' };
  const formattedDate = today.toLocaleDateString('en-US', options).replace(',', '');

  const handleSave = () => {
    // Save bill logic would go here
    navigation.goBack();
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color="#0284c7" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Add Bill</Text>
        <TouchableOpacity onPress={handleSave} style={styles.checkButton}>
          <Ionicons name="checkmark" size={24} color="#0284c7" />
        </TouchableOpacity>
      </View>

      {/* Tab Navigation */}
      <View style={styles.tabContainer}>
        {['EXPENSE', 'INCOME', 'TRANSFER', 'BILLS'].map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[
              styles.tab,
              activeTab === tab && styles.activeTab
            ]}
            onPress={() => setActiveTab(tab)}
          >
            <Text
              style={[
                styles.tabText,
                activeTab === tab && styles.activeTabText
              ]}
            >
              {tab}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <KeyboardAvoidingView 
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={styles.keyboardAvoid}
      >
        <ScrollView style={styles.formContainer}>
          {/* Amount Due */}
          <View style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Text style={styles.iconText}>$</Text>
            </View>
            <TextInput
              style={styles.input}
              placeholder="Amount due"
              placeholderTextColor="#9ca3af"
              keyboardType="decimal-pad"
              value={amount}
              onChangeText={setAmount}
            />
          </View>
          <View style={styles.separator} />

          {/* Category */}
          <TouchableOpacity style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="grid" size={20} color="#64748b" />
            </View>
            <Text style={styles.placeholderText}>Select category</Text>
            <Ionicons name="chevron-forward" size={20} color="#d1d5db" />
          </TouchableOpacity>
          <View style={styles.separator} />

          {/* Title */}
          <View style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="document-text-outline" size={20} color="#64748b" />
            </View>
            <TextInput
              style={styles.input}
              placeholder="Title..."
              placeholderTextColor="#9ca3af"
              value={title}
              onChangeText={setTitle}
            />
          </View>
          <View style={styles.separator} />

          {/* Due Date */}
          <TouchableOpacity style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="calendar-outline" size={20} color="#64748b" />
            </View>
            <View>
              <Text style={styles.inputText}>{formattedDate}</Text>
              <Text style={styles.inputLabel}>Due Date</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#d1d5db" />
          </TouchableOpacity>
          <View style={styles.separator} />

          {/* Repeat Option */}
          <TouchableOpacity style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="refresh" size={20} color="#64748b" />
            </View>
            <Text style={styles.placeholderText}>Select repeat option</Text>
            <Ionicons name="chevron-forward" size={20} color="#d1d5db" />
          </TouchableOpacity>
          <View style={styles.separator} />

          {/* Reminder */}
          <TouchableOpacity style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="notifications-outline" size={20} color="#64748b" />
            </View>
            <Text style={styles.inputText}>Remind 5 days before</Text>
            <Ionicons name="chevron-forward" size={20} color="#d1d5db" />
          </TouchableOpacity>
          <View style={styles.separator} />

          {/* Auto Paid */}
          <View style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="calendar-outline" size={20} color="#64748b" />
            </View>
            <Text style={styles.inputText}>Auto Paid</Text>
            <Switch
              value={autoPaid}
              onValueChange={setAutoPaid}
              trackColor={{ false: "#e5e7eb", true: "#0284c7" }}
              thumbColor="#ffffff"
            />
          </View>
          <View style={styles.noteContainer}>
            <Text style={styles.noteText}>
              Note: Auto-paid bills are marked as paid on the due date in the app.
            </Text>
          </View>
          <View style={styles.separator} />

          {/* From Account */}
          <TouchableOpacity style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="business-outline" size={20} color="#64748b" />
            </View>
            <Text style={styles.placeholderText}>From account</Text>
            <Ionicons name="chevron-forward" size={20} color="#d1d5db" />
          </TouchableOpacity>
          <View style={styles.separator} />

          {/* Add Expense Entry */}
          <View style={styles.inputRow}>
            <Text style={styles.inputText}>Add expense entry for this payment.</Text>
            <Switch
              value={addExpenseEntry}
              onValueChange={setAddExpenseEntry}
              trackColor={{ false: "#e5e7eb", true: "#0284c7" }}
              thumbColor="#ffffff"
            />
          </View>
          <View style={styles.separator} />

          {/* Notes */}
          <View style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="document-text-outline" size={20} color="#64748b" />
            </View>
            <TextInput
              style={styles.input}
              placeholder="Notes..."
              placeholderTextColor="#9ca3af"
              multiline
              value={notes}
              onChangeText={setNotes}
            />
          </View>
          <View style={styles.separator} />

          {/* Attach Photo */}
          <TouchableOpacity style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="camera-outline" size={20} color="#64748b" />
            </View>
            <Text style={styles.placeholderText}>Attach photo</Text>
          </TouchableOpacity>
          <View style={styles.separator} />

          {/* Extra space at bottom for scrolling */}
          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: 'white',
  },
  keyboardAvoid: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#e0f2fe',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  backButton: {
    padding: 4,
  },
  checkButton: {
    padding: 4,
  },
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: 'white',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  tab: {
    flex: 1,
    paddingVertical: 16,
    alignItems: 'center',
  },
  activeTab: {
    borderBottomWidth: 2,
    borderBottomColor: '#0284c7',
  },
  tabText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#64748b',
  },
  activeTabText: {
    color: '#0284c7',
  },
  formContainer: {
    flex: 1,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 16,
    paddingHorizontal: 16,
  },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  iconText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#64748b',
  },
  input: {
    flex: 1,
    fontSize: 16,
    color: '#1e293b',
  },
  placeholderText: {
    flex: 1,
    fontSize: 16,
    color: '#9ca3af',
  },
  inputText: {
    flex: 1,
    fontSize: 16,
    color: '#1e293b',
  },
  inputLabel: {
    fontSize: 14,
    color: '#64748b',
    marginTop: 2,
  },
  separator: {
    height: 1,
    backgroundColor: '#e2e8f0',
    marginLeft: 64,
  },
  noteContainer: {
    backgroundColor: '#fef3c7',
    padding: 12,
    marginLeft: 64,
    marginRight: 16,
    borderRadius: 4,
    marginTop: 4,
  },
  noteText: {
    fontSize: 14,
    color: '#92400e',
  },
});