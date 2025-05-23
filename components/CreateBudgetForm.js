import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Switch,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function CreateBudgetForm({ navigation, route }) {
  const { type } = route.params || { type: 'personal' };
  const [budgetName, setBudgetName] = useState('');
  const [amount, setAmount] = useState('');
  const [category, setCategory] = useState('');
  const [period, setPeriod] = useState('Monthly');
  const [rollover, setRollover] = useState(false);
  const [notifications, setNotifications] = useState(true);

  const handleSave = () => {
    // Save budget logic would go here
    navigation.navigate('Budget');
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color="#0284c7" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {type === 'group' ? 'Group Budget' : 'Personal Budget'}
        </Text>
        <TouchableOpacity onPress={handleSave} style={styles.checkButton}>
          <Ionicons name="checkmark" size={24} color="#0284c7" />
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView 
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={styles.keyboardAvoid}
      >
        <ScrollView style={styles.formContainer}>
          {/* Budget Name */}
          <View style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="document-text-outline" size={20} color="#64748b" />
            </View>
            <TextInput
              style={styles.input}
              placeholder="Budget Name"
              placeholderTextColor="#9ca3af"
              value={budgetName}
              onChangeText={setBudgetName}
            />
          </View>
          <View style={styles.separator} />

          {/* Amount */}
          <View style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Text style={styles.iconText}>$</Text>
            </View>
            <TextInput
              style={styles.input}
              placeholder="Amount"
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
              <Ionicons name="grid-outline" size={20} color="#64748b" />
            </View>
            <Text style={styles.placeholderText}>Select Category</Text>
            <Ionicons name="chevron-forward" size={20} color="#d1d5db" />
          </TouchableOpacity>
          <View style={styles.separator} />

          {/* Period */}
          <TouchableOpacity style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="calendar-outline" size={20} color="#64748b" />
            </View>
            <Text style={styles.inputText}>{period}</Text>
            <Ionicons name="chevron-forward" size={20} color="#d1d5db" />
          </TouchableOpacity>
          <View style={styles.separator} />

          {/* Rollover */}
          <View style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="refresh-outline" size={20} color="#64748b" />
            </View>
            <Text style={styles.inputText}>Rollover Unused Budget</Text>
            <Switch
              value={rollover}
              onValueChange={setRollover}
              trackColor={{ false: "#e5e7eb", true: "#0284c7" }}
              thumbColor="#ffffff"
            />
          </View>
          <View style={styles.separator} />

          {/* Notifications */}
          <View style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="notifications-outline" size={20} color="#64748b" />
            </View>
            <Text style={styles.inputText}>Budget Notifications</Text>
            <Switch
              value={notifications}
              onValueChange={setNotifications}
              trackColor={{ false: "#e5e7eb", true: "#0284c7" }}
              thumbColor="#ffffff"
            />
          </View>
          <View style={styles.separator} />

          {/* Group Members (only for group budget) */}
          {type === 'group' && (
            <>
              <TouchableOpacity style={styles.inputRow}>
                <View style={styles.iconContainer}>
                  <Ionicons name="people-outline" size={20} color="#64748b" />
                </View>
                <Text style={styles.placeholderText}>Add Group Members</Text>
                <Ionicons name="chevron-forward" size={20} color="#d1d5db" />
              </TouchableOpacity>
              <View style={styles.separator} />
            </>
          )}

          {/* Notes */}
          <View style={styles.inputRow}>
            <View style={styles.iconContainer}>
              <Ionicons name="document-text-outline" size={20} color="#64748b" />
            </View>
            <TextInput
              style={styles.input}
              placeholder="Notes (optional)"
              placeholderTextColor="#9ca3af"
              multiline
            />
          </View>
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
  separator: {
    height: 1,
    backgroundColor: '#e2e8f0',
    marginLeft: 64,
  },
});